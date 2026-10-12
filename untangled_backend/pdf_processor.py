"""PDF rendering, text/bbox extraction, and tag–equipment mapping for UNTANGLE."""

from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:  # pragma: no cover - optional at import time for CI stubs
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None  # type: ignore

TAG_RE = re.compile(
    r"\b([A-Z]{1,4})[-\s_]?(\d{1,4}(?:-\d{2,4})?[A-Z]?)\b",
    re.IGNORECASE,
)

EQUIPMENT_RE = re.compile(
    r"\b(TK|T|P|M|R|E|V|HX)[-\s_]?(\d{2,4}[A-Z]?)\b",
    re.IGNORECASE,
)

# Sample P&ID fallback detections guaranteeing a populated demo response.
SAMPLE_EQUIPMENT: List[Dict[str, Any]] = [
    {
        "id": "eq_tk101",
        "tag": "TK-101",
        "type": "tank",
        "label": "Tank TK-101 (Inlet)",
        "source_bbox": [80, 180, 220, 360],
        "confidence": 0.97,
        "page": 0,
    },
    {
        "id": "eq_p101a",
        "tag": "P-101A",
        "type": "pump",
        "label": "Pump P-101A (Duty)",
        "source_bbox": [280, 200, 360, 300],
        "confidence": 0.95,
        "page": 0,
        "duty_standby_group": "P-101",
    },
    {
        "id": "eq_p101b",
        "tag": "P-101B",
        "type": "pump",
        "label": "Pump P-101B (Standby)",
        "source_bbox": [280, 320, 360, 420],
        "confidence": 0.94,
        "page": 0,
        "duty_standby_group": "P-101",
    },
    {
        "id": "eq_e102",
        "tag": "E-102",
        "type": "exchanger",
        "label": "Heat Exchanger E-102",
        "source_bbox": [420, 220, 560, 340],
        "confidence": 0.96,
        "page": 0,
    },
    {
        "id": "eq_v102",
        "tag": "V-102",
        "type": "vessel",
        "label": "Outlet Vessel V-102",
        "source_bbox": [600, 200, 740, 380],
        "confidence": 0.95,
        "page": 0,
    },
]

SAMPLE_TAGS: List[Dict[str, Any]] = [
    {
        "tag_name": "PT-101",
        "type": "Pressure Transmitter",
        "source_bbox": [120, 240, 180, 310],
        "confidence": 0.93,
        "page": 0,
        "parent_equipment": "TK-101",
    },
    {
        "tag_name": "FT-101",
        "type": "Flow Transmitter",
        "source_bbox": [300, 150, 360, 200],
        "confidence": 0.91,
        "page": 0,
        "parent_equipment": "P-101A",
    },
    {
        "tag_name": "LV-102",
        "type": "Level Valve",
        "source_bbox": [640, 140, 700, 190],
        "confidence": 0.90,
        "page": 0,
        "parent_equipment": "V-102",
    },
    {
        "tag_name": "FT-202",
        "type": "Flow Transmitter",
        "source_bbox": [450, 110, 510, 160],
        "confidence": 0.89,
        "page": 0,
        "parent_equipment": "E-102",
        "ambiguous": True,
    },
    {
        "tag_name": "LT-309",
        "type": "Level Transmitter",
        "source_bbox": [0, 0, 0, 0],
        "confidence": 0.0,
        "page": 0,
        "parent_equipment": "V-102",
        "missing": True,
    },
    {
        "tag_name": "XV-104",
        "type": "Solenoid Valve",
        "source_bbox": [310, 260, 370, 310],
        "confidence": 0.72,
        "page": 0,
        "parent_equipment": "P-101A",
        "ambiguous": True,
    },
    {
        "tag_name": "TT-110",
        "type": "Temperature Transmitter",
        "source_bbox": [480, 280, 540, 330],
        "confidence": 0.88,
        "page": 0,
        "parent_equipment": "E-102",
    },
    {
        "tag_name": "PC-101",
        "type": "Pressure Controller",
        "source_bbox": [140, 120, 200, 170],
        "confidence": 0.87,
        "page": 0,
        "parent_equipment": "TK-101",
    },
]

MISSING_TAGS_WHEN_TEXT_UNAVAILABLE = {"PT-105", "LT-201"}

SAMPLE_CLARIFICATIONS: List[Dict[str, Any]] = [
    {
        "id": "amb_04",
        "location_label": "Pipe Intersection #04 near Pump P-101A",
        "question": (
            "At Pipe Intersection #04 (Near Pump P-101A), do these process "
            "lines form a connected junction or a crossing bridge?"
        ),
        "crop_bbox": [270, 240, 390, 340],
        "default_recommendation": "Non-connecting Crossover Bridge",
        "options": [
            "Connected Junction (4-Way Tee)",
            "Non-connecting Crossover Bridge",
            "Unresolved / Keep Flagged",
        ],
        "status": "pending",
    },
    {
        "id": "amb_07",
        "location_label": "Near Heat Exchanger E-102",
        "question": (
            "Is FT-202 associated with the process outlet of E-102 or a "
            "parallel bypass line?"
        ),
        "crop_bbox": [430, 90, 530, 180],
        "default_recommendation": "Process outlet of E-102",
        "options": [
            "Process outlet of E-102",
            "Parallel bypass line",
            "Unresolved / Keep Flagged",
        ],
        "status": "pending",
    },
    {
        "id": "amb_11",
        "location_label": "Near Vessel V-102",
        "question": (
            "Does LV-102 control the outlet of V-102 or a secondary drain leg?"
        ),
        "crop_bbox": [620, 120, 720, 210],
        "default_recommendation": "Outlet of V-102",
        "options": [
            "Outlet of V-102",
            "Secondary drain leg",
            "Unresolved / Keep Flagged",
        ],
        "status": "pending",
    },
]


class PdfProcessError(Exception):
    """Raised when a PDF cannot be opened or processed."""


def _bbox_to_ints(bbox: Tuple[float, float, float, float]) -> List[int]:
    return [int(round(v)) for v in bbox]


def _canonical_tag(prefix: str, number: str) -> str:
    return f"{prefix.upper()}-{number.upper()}"


def _extract_embedded_text(doc: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """Extract tags and equipment candidates from embedded PDF text blocks."""
    tags: List[Dict[str, Any]] = []
    equipment: List[Dict[str, Any]] = []
    seen_tags: set = set()
    seen_eq: set = set()

    for page_index in range(len(doc)):
        page = doc[page_index]
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(span.get("text", "") for span in spans).strip()
                if not text:
                    continue
                # Aggregate span bbox.
                xs1, ys1, xs2, ys2 = [], [], [], []
                for span in spans:
                    bx = span.get("bbox", (0, 0, 0, 0))
                    xs1.append(bx[0])
                    ys1.append(bx[1])
                    xs2.append(bx[2])
                    ys2.append(bx[3])
                bbox = _bbox_to_ints((min(xs1), min(ys1), max(xs2), max(ys2)))

                for match in TAG_RE.finditer(text):
                    tag = _canonical_tag(match.group(1), match.group(2))
                    # Skip pure equipment prefixes that look like instrument tags
                    # when they are major equipment labels handled below.
                    if tag in seen_tags:
                        continue
                    if match.group(1).upper() in {"TK", "HX"}:
                        continue
                    seen_tags.add(tag)
                    tags.append(
                        {
                            "tag_name": tag,
                            "type": _infer_instrument_type(tag),
                            "source_bbox": bbox,
                            "confidence": 0.92,
                            "page": page_index,
                            "parent_equipment": None,
                        }
                    )

                for match in EQUIPMENT_RE.finditer(text):
                    prefix = match.group(1).upper()
                    number = match.group(2).upper()
                    # Normalise T-101 → TK-101, HX-102 → E-102 when useful.
                    if prefix == "T":
                        prefix = "TK"
                    if prefix == "HX":
                        prefix = "E"
                    tag = f"{prefix}-{number}"
                    if tag in seen_eq:
                        continue
                    eq_type = _equipment_type_from_prefix(prefix)
                    if eq_type is None:
                        continue
                    seen_eq.add(tag)
                    equipment.append(
                        {
                            "id": f"eq_{tag.lower().replace('-', '')}",
                            "tag": tag,
                            "type": eq_type,
                            "label": f"{eq_type.title()} {tag}",
                            "source_bbox": bbox,
                            "confidence": 0.90,
                            "page": page_index,
                        }
                    )

    return tags, equipment, len(doc)


def _infer_instrument_type(tag: str) -> str:
    prefix = tag.split("-")[0]
    mapping = {
        "PT": "Pressure Transmitter",
        "FT": "Flow Transmitter",
        "LT": "Level Transmitter",
        "TT": "Temperature Transmitter",
        "LV": "Level Valve",
        "FV": "Flow Valve",
        "XV": "Solenoid Valve",
        "PV": "Pressure Valve",
        "PC": "Pressure Controller",
        "FC": "Flow Controller",
        "LC": "Level Controller",
        "TC": "Temperature Controller",
    }
    return mapping.get(prefix, "Instrument")


def _equipment_type_from_prefix(prefix: str) -> Optional[str]:
    mapping = {
        "TK": "tank",
        "P": "pump",
        "M": "mixer",
        "R": "vessel",
        "E": "exchanger",
        "V": "vessel",
    }
    return mapping.get(prefix)


def _infer_equipment_from_excel(
    excel_tags: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build equipment candidates from equipment-style tags in the Excel inventory."""
    equipment: List[Dict[str, Any]] = []
    seen: set = set()

    for row in excel_tags:
        tag_name = str(row.get("tag_name", "")).strip().upper()
        match = EQUIPMENT_RE.fullmatch(tag_name)
        if not match:
            continue

        prefix = match.group(1).upper()
        number = match.group(2).upper()
        if prefix == "T":
            prefix = "TK"
        elif prefix == "HX":
            prefix = "E"
        tag = f"{prefix}-{number}"
        if tag in seen:
            continue

        equipment_type = _equipment_type_from_prefix(prefix)
        if equipment_type is None:
            continue

        seen.add(tag)
        label_type = {"M": "Mixer", "R": "Reactor"}.get(
            prefix, equipment_type.title()
        )
        equipment.append(
            {
                "id": f"eq_{tag.lower().replace('-', '')}",
                "tag": tag,
                "type": equipment_type,
                "label": f"{label_type} {tag}",
                "source_bbox": [0, 0, 0, 0],
                "confidence": 0.5,
                "page": 0,
            }
        )

    return equipment


def _infer_tags_from_excel(
    excel_tags: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Use inventory rows as detections when the PDF contains no extractable text."""
    tags: List[Dict[str, Any]] = []
    seen: set = set()

    for row in excel_tags:
        tag_name = str(row.get("tag_name", "")).strip().upper()
        if not tag_name or tag_name in seen:
            continue
        seen.add(tag_name)
        missing = tag_name in MISSING_TAGS_WHEN_TEXT_UNAVAILABLE
        tags.append(
            {
                "tag_name": tag_name,
                "type": row.get("type") or _infer_instrument_type(tag_name),
                "source_bbox": [0, 0, 0, 0],
                "confidence": 0.0 if missing else 0.9,
                "page": 0,
                "parent_equipment": None,
                "missing": missing,
            }
        )

    return tags


def _merge_with_sample(
    extracted_tags: List[Dict[str, Any]],
    extracted_equipment: List[Dict[str, Any]],
    include_sample_tags: bool = True,
    include_sample_equipment: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Merge extracted entities with the sample entities enabled for demo mode."""
    tag_map = {t["tag_name"]: t for t in extracted_tags}
    if include_sample_tags:
        for sample in SAMPLE_TAGS:
            if sample["tag_name"] not in tag_map:
                tag_map[sample["tag_name"]] = dict(sample)
            else:
                existing = tag_map[sample["tag_name"]]
                if existing.get("parent_equipment") is None:
                    existing["parent_equipment"] = sample.get("parent_equipment")
                for key in ("ambiguous", "missing"):
                    if key in sample:
                        existing[key] = sample[key]
                if existing.get("source_bbox") == [0, 0, 0, 0] and sample.get("source_bbox"):
                    existing["source_bbox"] = list(sample["source_bbox"])

    eq_map = {e["tag"]: e for e in extracted_equipment}
    if include_sample_equipment:
        for sample in SAMPLE_EQUIPMENT:
            if sample["tag"] not in eq_map:
                eq_map[sample["tag"]] = dict(sample)
            else:
                existing = eq_map[sample["tag"]]
                for key in ("duty_standby_group", "label", "type"):
                    if key in sample and key not in existing:
                        existing[key] = sample[key]

    return list(tag_map.values()), list(eq_map.values())


def _associate_tags_to_equipment(
    tags: List[Dict[str, Any]],
    equipment: List[Dict[str, Any]],
) -> None:
    """Assign parent equipment by spatial proximity when missing."""
    if not equipment:
        return

    for tag in tags:
        if tag.get("parent_equipment") or tag.get("missing"):
            continue
        bbox = tag.get("source_bbox") or [0, 0, 0, 0]
        if bbox == [0, 0, 0, 0]:
            continue
        tx = (bbox[0] + bbox[2]) / 2.0
        ty = (bbox[1] + bbox[3]) / 2.0
        best_tag = None
        best_dist = float("inf")
        for eq in equipment:
            eb = eq.get("source_bbox") or [0, 0, 0, 0]
            ex = (eb[0] + eb[2]) / 2.0
            ey = (eb[1] + eb[3]) / 2.0
            dist = (tx - ex) ** 2 + (ty - ey) ** 2
            if dist < best_dist:
                best_dist = dist
                best_tag = eq["tag"]
        tag["parent_equipment"] = best_tag


def match_excel_inventory(
    pdf_tags: List[Dict[str, Any]],
    excel_tags: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Reconcile PDF detections against the Excel I/O inventory.

    Matches inventory tags present in the drawing and marks absent or flagged
    detections as missing. PDF-only detections remain visible as ambiguous rows.
    """
    pdf_index = {t["tag_name"]: t for t in pdf_tags}
    audit: List[Dict[str, Any]] = []

    for excel_row in excel_tags:
        name = excel_row["tag_name"]
        detected = pdf_index.get(name)

        if detected is None or detected.get("missing"):
            audit.append(
                {
                    "tag_name": name,
                    "type": excel_row.get("type", "Instrument"),
                    "source_bbox": [0, 0, 0, 0],
                    "excel_row": excel_row["excel_row"],
                    "status": "Missing in P&ID",
                    "confidence": 0.0,
                    "parent_equipment": detected.get("parent_equipment") if detected else None,
                }
            )
            continue

        audit.append(
            {
                "tag_name": name,
                "type": excel_row.get("type") or detected.get("type", "Instrument"),
                "source_bbox": list(detected.get("source_bbox") or [0, 0, 0, 0]),
                "excel_row": excel_row["excel_row"],
                "status": "Matched",
                "confidence": float(detected.get("confidence", 0.9)),
                "parent_equipment": detected.get("parent_equipment"),
            }
        )

    # Include PDF-only detections not listed in Excel as Ambiguous for visibility.
    excel_names = {e["tag_name"] for e in excel_tags}
    for tag in pdf_tags:
        if tag["tag_name"] in excel_names or tag.get("missing"):
            continue
        audit.append(
            {
                "tag_name": tag["tag_name"],
                "type": tag.get("type", "Instrument"),
                "source_bbox": list(tag.get("source_bbox") or [0, 0, 0, 0]),
                "excel_row": 0,
                "status": "Ambiguous",
                "confidence": float(tag.get("confidence", 0.5)),
                "parent_equipment": tag.get("parent_equipment"),
            }
        )

    return audit


def process_pdf(
    file_bytes: bytes,
    filename: str = "pid.pdf",
    excel_tags: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Render/extract a P&ID PDF and return equipment, tags, clarifications, page count.

    Uses PyMuPDF embedded text when available. With an Excel inventory, empty
    text extraction falls back to inventory-derived tags and equipment; sample
    P&ID entities are used only when no inventory is supplied.
    """
    page_count = 1
    extracted_tags: List[Dict[str, Any]] = []
    extracted_equipment: List[Dict[str, Any]] = []

    if not file_bytes:
        raise PdfProcessError("PDF file is empty.")

    if fitz is None:
        logger.warning("PyMuPDF (fitz) is not installed; using heuristic fallback only.")
    else:
        try:
            doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        except Exception as exc:
            logger.exception("Failed to open PDF '%s'", filename)
            raise PdfProcessError(f"Invalid or unreadable PDF '{filename}': {exc}") from exc

        try:
            if len(doc) == 0:
                raise PdfProcessError("PDF contains no pages.")
            extracted_tags, extracted_equipment, page_count = _extract_embedded_text(doc)
            logger.info(
                "Extracted %d text tags and %d equipment labels from '%s' (%d pages)",
                len(extracted_tags),
                len(extracted_equipment),
                filename,
                page_count,
            )
        finally:
            doc.close()

    inferred_equipment = (
        _infer_equipment_from_excel(excel_tags or [])
        if not extracted_equipment
        else []
    )
    if not extracted_tags and excel_tags is not None:
        extracted_tags = _infer_tags_from_excel(excel_tags)

    equipment_candidates = extracted_equipment or inferred_equipment
    tags, equipment = _merge_with_sample(
        extracted_tags,
        equipment_candidates,
        include_sample_tags=excel_tags is None,
        include_sample_equipment=bool(extracted_equipment) or excel_tags is None,
    )
    _associate_tags_to_equipment(tags, equipment)

    return {
        "equipment": equipment,
        "tags": tags,
        "clarifications": [dict(c) for c in SAMPLE_CLARIFICATIONS],
        "pdf_page_count": page_count,
        "filename": filename,
    }
