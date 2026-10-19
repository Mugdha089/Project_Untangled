"""
Project UNTANGLE — FastAPI backend entrypoint.

AI-Powered P&ID Digitisation & Process Simplification System.
"""

from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import time
import uuid
from pathlib import Path
from typing import Dict
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from excel_parser import ExcelParseError, load_excel_tags
from auth import current_user, issue_token
from graph_engine import build_process_graph
from pdf_processor import (
    PdfProcessError,
    has_valid_source_bbox,
    match_excel_inventory,
    process_pdf,
)
from topology_evidence import CONNECTED_JUNCTION, CROSSOVER
import run_storage
from schemas import (
    ClarificationItem,
    EquipmentNode,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    KpiSummary,
    ProcessEdge,
    ProcessPidResponse,
    RunListResponse,
    ResolveAmbiguityRequest,
    ResolveAmbiguityResponse,
    TagAuditItem,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("untangle.main")

API_VERSION = "v1.0"
MODEL_STATUS = "PyMuPDF text/vector pipeline; OCR unavailable"
BACKEND_ENV_FILE = Path(__file__).with_name(".env")


def load_backend_environment(dotenv_path: Path | None = None) -> None:
    """Load backend settings without overriding explicit process environment."""
    load_dotenv(dotenv_path=dotenv_path or BACKEND_ENV_FILE, override=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_backend_environment()
    run_storage.initialize_database()
    yield


app = FastAPI(
    title="Project UNTANGLE API",
    description=(
        "Evidence-driven P&ID digitisation and process simplification backend. "
        "Accepts a P&ID PDF and I/O Excel list, extracts tags/equipment, builds "
        "a topology-preserving process graph, and returns an auditable PFD payload."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Explicit localhost origins for the frontend development servers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return system status, model status, and API version."""
    return HealthResponse(
        status="ok",
        model_status=MODEL_STATUS,
        api_version=API_VERSION,
        service="UNTANGLE Backend",
    )


def _source_tag_detections(pdf_result: dict) -> list[dict]:
    """Combine instrument and equipment tag labels with their extracted PDF boxes."""
    detections = [dict(item) for item in pdf_result.get("tags", [])]
    seen = {str(item.get("tag_name", "")).upper() for item in detections}
    for equipment in pdf_result.get("equipment", []):
        tag = str(equipment.get("tag", "")).strip()
        bbox = equipment.get("source_bbox")
        if not tag or tag.upper() in seen or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            valid_bbox = float(bbox[2]) > float(bbox[0]) and float(bbox[3]) > float(bbox[1])
        except (TypeError, ValueError):
            valid_bbox = False
        if not valid_bbox:
            continue
        detections.append(
            {
                "tag_name": tag,
                "type": str(equipment.get("type") or "Equipment"),
                "source_bbox": list(bbox),
                "source_page": equipment.get("source_page", equipment.get("page")),
                "confidence": equipment.get("confidence", 0.0),
            }
        )
        seen.add(tag.upper())
    return detections


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    user = run_storage.find_user(payload.email)
    if user is None or not run_storage.verify_password(
        payload.password, user["password_salt"], user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token, expires_at = issue_token(user)
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user={key: user[key] for key in ("user_id", "email", "full_name", "role")},
    )


@app.get("/api/auth/me")
async def get_current_session(user: dict = Depends(current_user)) -> dict:
    return user


@app.post("/api/process-pid", response_model=ProcessPidResponse)
async def process_pid(
    file_pdf: UploadFile = File(..., description="P&ID blueprint PDF"),
    file_excel: UploadFile = File(..., description="I/O tag Excel spreadsheet (.xlsx)"),
    demo_mode: bool = Form(False, description="Use sample entities and clarifications for demo only"),
    user: dict = Depends(current_user),
) -> ProcessPidResponse:
    """
    End-to-end pipeline:

    1. Parse Excel I/O inventory
    2. Extract PDF text, equipment labels, and vector-line evidence
    3. Match tags and build audit report
    4. Construct NetworkX topology from classified process-line geometry
    5. Return ProcessPidResponse (target < 3 s)
    """
    started = time.perf_counter()
    logger.info(
        "POST /api/process-pid pdf=%s excel=%s",
        file_pdf.filename,
        file_excel.filename,
    )

    # --- Validate content types / extensions ---------------------------------
    pdf_name = file_pdf.filename or "pid.pdf"
    excel_name = file_excel.filename or "io_list.xlsx"

    if not pdf_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="file_pdf must be a .pdf file.")
    if not (
        excel_name.lower().endswith(".xlsx")
        or excel_name.lower().endswith(".xls")
    ):
        raise HTTPException(
            status_code=400,
            detail="file_excel must be an Excel workbook (.xlsx or .xls).",
        )

    try:
        pdf_bytes = await file_pdf.read()
    except Exception as exc:
        logger.exception("Failed reading PDF upload")
        raise HTTPException(status_code=400, detail=f"Unable to read PDF upload: {exc}") from exc

    try:
        excel_bytes = await file_excel.read()
    except Exception as exc:
        logger.exception("Failed reading Excel upload")
        raise HTTPException(
            status_code=400, detail=f"Unable to read Excel upload: {exc}"
        ) from exc

    # --- Excel parsing -------------------------------------------------------
    try:
        inventory = load_excel_tags(excel_bytes, filename=excel_name)
    except ExcelParseError as exc:
        logger.warning("Excel parse failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Unable to parse Excel inventory: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected Excel error")
        raise HTTPException(
            status_code=400,
            detail=f"Unreadable Excel file: {exc}",
        ) from exc

    if not inventory.get("tags"):
        raise HTTPException(
            status_code=400,
            detail="Excel workbook contains no usable instrument tags.",
        )

    excel_tags = inventory["tags"]

    # --- PDF processing ------------------------------------------------------
    try:
        pdf_result = process_pdf(
            pdf_bytes,
            filename=pdf_name,
            excel_tags=excel_tags,
            demo_mode=demo_mode,
        )
    except PdfProcessError as exc:
        logger.exception("PDF processing failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected PDF error")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid PDF format or processing failure: {exc}",
        ) from exc

    # --- Tag audit -----------------------------------------------------------
    source_tag_detections = _source_tag_detections(pdf_result)
    audit_rows = match_excel_inventory(source_tag_detections, excel_tags)

    # --- Graph + semantic reduction ------------------------------------------
    graph_result = build_process_graph(
        pdf_result["equipment"],
        audit_rows,
        pdf_result.get("drawing_evidence"),
    )

    elapsed = round(time.perf_counter() - started, 3)

    matched = sum(1 for row in audit_rows if row["status"] == "Matched")
    missing = sum(1 for row in audit_rows if row["status"] == "Missing in P&ID")
    # This KPI counts ambiguous inventory groups. PDF-only detections also use
    # Ambiguous in the row status, but are reported separately below.
    ambiguous = sum(
        1 for row in audit_rows
        if row["status"] == "Ambiguous" and int(row.get("excel_row", 0)) > 0
    )
    pdf_only_tags = sum(
        1 for row in audit_rows if row.get("reason") == "unmatched_pdf_detection"
    )
    pending_review = sum(1 for row in audit_rows if row["status"] == "Pending Review")
    inventory_rows = int(inventory.get("total_rows", len(excel_tags)))
    usable_inventory_rows = len(excel_tags)
    inventory_frequency = Counter(row["tag_name"] for row in excel_tags)
    unique_inventory_tags = len(inventory_frequency)
    duplicate_inventory_tags = sum(1 for count in inventory_frequency.values() if count > 1)
    duplicate_inventory_rows = sum(count - 1 for count in inventory_frequency.values() if count > 1)
    total_tags = unique_inventory_tags
    detected_source_tags = len({
        row["tag_name"]
        for row in source_tag_detections
        if has_valid_source_bbox(row.get("source_bbox"))
    })
    retained = int(graph_result["retained_equipment"])

    kpis = KpiSummary(
        total_tags=total_tags,
        matched_tags=matched,
        retained_equipment=retained,
        graph_integrity=graph_result["graph_integrity"],
        processing_time_seconds=elapsed,
        inventory_rows=inventory_rows,
        usable_inventory_rows=usable_inventory_rows,
        unique_inventory_tags=unique_inventory_tags,
        duplicate_inventory_tags=duplicate_inventory_tags,
        duplicate_inventory_rows=duplicate_inventory_rows,
        detected_source_tags=detected_source_tags,
        missing_tags=missing,
        ambiguous_tags=ambiguous,
        pdf_only_tags=pdf_only_tags,
        pending_review_tags=pending_review,
        audit_rows=len(audit_rows),
        clarification_items=len(pdf_result.get("clarifications", [])),
    )

    nodes = [EquipmentNode(**n) for n in graph_result["nodes"]]
    edges = [ProcessEdge(**e) for e in graph_result["edges"]]
    tag_audit = [
        TagAuditItem(
            tag_name=row["tag_name"],
            type=row["type"],
            source_bbox=[int(v) for v in row["source_bbox"]],
            source_page=row.get("source_page"),
            excel_row=int(row["excel_row"]),
            excel_rows=[int(v) for v in row.get("excel_rows", [row["excel_row"]])],
            excel_sheet=row.get("excel_sheet"),
            excel_sheets=row.get("excel_sheets", []),
            status=row["status"],
            confidence=float(row["confidence"]),
            reason=row.get("reason"),
        )
        for row in audit_rows
    ]
    clarifications = [
        ClarificationItem(**item) for item in pdf_result.get("clarifications", [])
    ]

    logger.info(
        "Pipeline complete in %.3fs — tags=%d matched=%d equipment=%d pages=%d",
        elapsed,
        total_tags,
        matched,
        retained,
        pdf_result["pdf_page_count"],
    )

    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    response = ProcessPidResponse(
        run_id=run_id,
        created_at=created_at,
        kpis=kpis,
        nodes=nodes,
        edges=edges,
        tag_audit=tag_audit,
        clarification_queue=clarifications,
        pdf_page_count=int(pdf_result["pdf_page_count"]),
        pdf_filename=pdf_name,
        excel_filename=excel_name,
    )
    try:
        run_storage.save_run(
            response.model_dump(mode="json"),
            pdf_filename=pdf_name,
            excel_filename=excel_name,
            pdf_bytes=pdf_bytes,
            excel_bytes=excel_bytes,
            owner_id=user["user_id"],
        )
    except Exception as exc:
        logger.exception("Failed to persist processing run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail="Processing completed, but the run could not be saved.",
        ) from exc
    return response


@app.get("/api/runs", response_model=RunListResponse)
async def list_saved_runs(
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(current_user),
) -> RunListResponse:
    return RunListResponse(runs=run_storage.list_runs(user["user_id"], limit))


@app.get("/api/runs/{run_id}", response_model=ProcessPidResponse)
async def retrieve_saved_run(run_id: str, user: dict = Depends(current_user)) -> ProcessPidResponse:
    result = run_storage.get_run(run_id, user["user_id"])
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found.")
    return ProcessPidResponse.model_validate(result)


@app.get("/api/runs/{run_id}/files/{file_type}")
async def retrieve_run_file(run_id: str, file_type: str, user: dict = Depends(current_user)) -> Response:
    if file_type not in {"pdf", "excel"}:
        raise HTTPException(status_code=404, detail="Run file type was not found.")
    files = run_storage.get_run_files(run_id, user["user_id"])
    if files is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found.")
    key = "pdf" if file_type == "pdf" else "excel"
    filename = files[f"{key}_filename"]
    content = files[f"{key}_bytes"]
    media_type = "application/pdf" if key == "pdf" else (
        "application/vnd.ms-excel"
        if filename.lower().endswith(".xls") and not filename.lower().endswith(".xlsx")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"},
    )


@app.post("/api/resolve-ambiguity", response_model=ResolveAmbiguityResponse)
async def resolve_ambiguity(payload: ResolveAmbiguityRequest, user: dict = Depends(current_user)) -> ResolveAmbiguityResponse:
    """Apply a listed source-evidence decision to the graph and persist it."""
    resolved_id = payload.item_id.strip()
    option = payload.selected_option.strip()

    if not resolved_id or not option:
        raise HTTPException(
            status_code=400,
            detail="Both 'item_id' and 'selected_option' are required.",
        )

    logger.info("POST /api/resolve-ambiguity run=%s id=%s option=%s", payload.run_id, resolved_id, option)

    saved_run = run_storage.get_run(payload.run_id, user["user_id"])
    if saved_run is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{payload.run_id}' was not found.",
        )

    clarification = next(
        (item for item in saved_run["clarification_queue"] if item["id"] == resolved_id),
        None,
    )
    if clarification is None:
        raise HTTPException(
            status_code=404,
            detail=f"Clarification '{resolved_id}' is not available for run '{payload.run_id}'.",
        )
    options = clarification["options"]
    if option not in options:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid choice for clarification '{resolved_id}'. Choose one of: {', '.join(options)}",
        )

    unresolved = option == "Unresolved / Keep Flagged"
    is_crossing = resolved_id.startswith("crossing_p")
    is_nozzle = resolved_id.startswith("nozzle_")
    topology_changed = False
    nodes = [EquipmentNode(**node) for node in saved_run["nodes"]]

    if not unresolved and not (is_crossing or is_nozzle):
        raise HTTPException(
            status_code=422,
            detail="This clarification has no supported graph-resolution contract.",
        )

    if (is_crossing or is_nozzle) and not unresolved:
        run_files = run_storage.get_run_files(payload.run_id, user["user_id"])
        if run_files is None:
            raise HTTPException(status_code=404, detail="The source files for this run were not found.")
        try:
            source_result = process_pdf(
                run_files["pdf_bytes"], filename=run_files["pdf_filename"]
            )
            if not any(
                item["id"] == resolved_id
                for item in source_result["clarifications"]
            ):
                raise HTTPException(
                    status_code=422,
                    detail="The selected clarification is not supported by the saved PDF evidence.",
                )
            excel_result = load_excel_tags(
                run_files["excel_bytes"], filename=run_files["excel_filename"]
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unable to regenerate source graph for run %s", payload.run_id)
            raise HTTPException(
                status_code=422,
                detail="The saved source evidence could not be reprocessed.",
            ) from exc

        resolutions = {
            decision["item_id"]: decision["selected_option"]
            for decision in saved_run.get("clarification_decisions", [])
            if decision.get("status") == "resolved"
            and decision.get("item_id", "").startswith("crossing_p")
        }
        nozzle_resolutions = {
            decision["item_id"]: decision["selected_option"]
            for decision in saved_run.get("clarification_decisions", [])
            if decision.get("status") == "resolved"
            and decision.get("item_id", "").startswith("nozzle_")
        }
        if is_crossing:
            resolutions[resolved_id] = option
        else:
            nozzle_resolutions[resolved_id] = option
        regenerated_audit = match_excel_inventory(
            _source_tag_detections(source_result), excel_result["tags"]
        )
        graph_result = build_process_graph(
            source_result["equipment"],
            regenerated_audit,
            source_result.get("drawing_evidence"),
            crossing_resolutions=resolutions,
            nozzle_resolutions=nozzle_resolutions,
        )
        nodes = [EquipmentNode(**node) for node in graph_result["nodes"]]
        regenerated_edges = [ProcessEdge(**edge) for edge in graph_result["edges"]]
        old_node_ids = {node["id"] for node in saved_run["nodes"]}
        old_edges = {
            (edge["source"], edge["target"])
            for edge in saved_run["edges"]
        }
        new_node_ids = {node.id for node in nodes}
        new_edges = {(edge.source, edge.target) for edge in regenerated_edges}
        topology_changed = old_node_ids != new_node_ids or old_edges != new_edges
        kpi_data = dict(saved_run["kpis"])
        kpi_data["graph_integrity"] = graph_result["graph_integrity"]
        kpi_data["retained_equipment"] = graph_result["retained_equipment"]
        result = {
            "kpis": kpi_data,
            "edges": [edge.model_dump() for edge in regenerated_edges],
        }
    else:
        result = {
            "kpis": dict(saved_run["kpis"]),
            "edges": [dict(edge) for edge in saved_run["edges"]],
        }

    for count_name in (
        "inventory_rows",
        "usable_inventory_rows",
        "unique_inventory_tags",
        "duplicate_inventory_tags",
        "duplicate_inventory_rows",
        "detected_source_tags",
        "missing_tags",
        "ambiguous_tags",
        "pdf_only_tags",
        "pending_review_tags",
        "audit_rows",
        "clarification_items",
    ):
        result["kpis"][count_name] = int(
            saved_run["kpis"].get(count_name, 0)
        )

    kpis = KpiSummary(**result["kpis"])
    edges = [ProcessEdge(**e) for e in result["edges"]]
    updated_queue = []
    for item in saved_run["clarification_queue"]:
        if item["id"] != resolved_id:
            updated_queue.append(item)
        elif unresolved:
            updated_queue.append({**item, "status": "unresolved", "selected_option": option})
    kpis.clarification_items = len(updated_queue)
    updated_result = {
        **saved_run,
        "kpis": kpis.model_dump(),
        "nodes": [node.model_dump() for node in nodes],
        "edges": [edge.model_dump() for edge in edges],
        "clarification_queue": updated_queue,
    }
    try:
        run_storage.record_decision(
            payload.run_id,
            resolved_id,
            option,
            "unresolved" if unresolved else "resolved",
            updated_result,
            user["user_id"],
        )
    except run_storage.RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run '{payload.run_id}' was not found.") from exc
    except run_storage.ClarificationAlreadyResolvedError as exc:
        raise HTTPException(status_code=404, detail=f"Clarification '{resolved_id}' is already resolved.") from exc
    except run_storage.ClarificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Clarification '{resolved_id}' was not found.") from exc
    except Exception as exc:
        logger.exception("Failed to persist clarification for run %s", payload.run_id)
        raise HTTPException(status_code=500, detail="Clarification could not be saved.") from exc

    if unresolved:
        message = (
            f"Decision '{option}' recorded for '{resolved_id}'. The item remains "
            f"unresolved and the graph is unchanged. {kpis.graph_integrity}"
        )
    elif is_crossing:
        message = (
            f"User-confirmed decision '{option}' applied to the source-supported "
            f"crossing and the graph was regenerated. {kpis.graph_integrity}"
        )
    elif is_nozzle:
        message = (
            f"User-confirmed decision '{option}' applied to the source-supported "
            f"equipment endpoint and the graph was regenerated. {kpis.graph_integrity}"
        )
    else:
        message = f"Decision '{option}' recorded for '{resolved_id}'. {kpis.graph_integrity}"

    return ResolveAmbiguityResponse(
        run_id=payload.run_id,
        kpis=kpis,
        nodes=nodes,
        edges=edges,
        resolved_item_id=resolved_id,
        selected_option=option,
        message=message,
        topology_changed=topology_changed,
    )


@app.get("/")
async def root() -> Dict[str, str]:
    """Root redirect hint for operators."""
    return {
        "service": "Project UNTANGLE Backend",
        "health": "/api/health",
        "process": "POST /api/process-pid",
        "resolve": "POST /api/resolve-ambiguity",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
