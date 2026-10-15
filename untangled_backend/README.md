# Project UNTANGLE — Backend

FastAPI service for evidence-driven P&ID digitisation and process simplification.

## Modules

| File | Role |
|------|------|
| `main.py` | FastAPI app, CORS, `/api/health`, `/api/process-pid`, `/api/resolve-ambiguity` |
| `schemas.py` | Pydantic request/response models |
| `excel_parser.py` | pandas/openpyxl I/O tag normalisation |
| `pdf_processor.py` | PyMuPDF text/tag/equipment extraction and vector-line evidence |
| `graph_engine.py` | Source-geometry process graph and junction preservation |

## Live upload evidence

The upload endpoint only uses entities extracted from the uploaded PDF; it
does not add the hard-coded sample entities. A tag is reported as matched only
when its extracted PDF detection has a valid, non-empty source bounding box.
Image-only PDFs currently return an explicit error because OCR is not
configured. The sample entities in `pdf_processor.py` are available only when
`process_pdf(..., demo_mode=True)` is explicitly selected; the upload endpoint
does not enable that mode.

## Process topology evidence

Equipment and instrument candidates come from tag-like PDF text, with nearby
PDF label/vector-symbol evidence used to classify filters and valves. The Excel
workbook is used for tag reconciliation only; its equipment and connection
sheets are not supplied to extraction or graph construction.

Pipe segments are used only when their vector style can be associated with a
process-line legend entry. Utility and instrument-signal legend styles are
kept separate. Segment endpoints that meet are connected; an unmarked
interior crossing is not assumed to be a junction. Equipment and junctions
retain source-page and bounding-box coordinates. A pipe edge is emitted only
when a detected equipment-symbol bound intersects or adjoins that classified
process path. Text-only proximity is not enough to create an edge.

The source fixtures do not contain reliable flow-direction arrows. Accordingly,
returned process edges use `flow_direction="undirected"` and the KPI reports a
partial or unverified status instead of a percentage. A drawing without a
classifiable process-line legend, or without reliable equipment-to-line
associations, receives no guessed edges. Raster-only PDFs remain unsupported
until OCR is configured.

## Setup

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

## Endpoints

- `GET /api/health` — status, `TensorRT Active`, API `v1.0`
- `POST /api/process-pid` — multipart `file_pdf` + `file_excel` → `ProcessPidResponse`
- `POST /api/resolve-ambiguity` — JSON `{ "item_id", "selected_option" }` → updated KPIs/edges
