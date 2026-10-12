# Project UNTANGLE — Backend

FastAPI service for evidence-driven P&ID digitisation and process simplification.

## Modules

| File | Role |
|------|------|
| `main.py` | FastAPI app, CORS, `/api/health`, `/api/process-pid`, `/api/resolve-ambiguity` |
| `schemas.py` | Pydantic request/response models |
| `excel_parser.py` | pandas/openpyxl I/O tag normalisation |
| `pdf_processor.py` | PyMuPDF text/bbox extraction + sample heuristics |
| `graph_engine.py` | NetworkX graph, semantic loop reduction, auto-layout |

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
