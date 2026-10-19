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
when its extracted PDF detection has a valid, non-empty source bounding box and
the inventory tag is unique. Duplicate inventory tags are marked ambiguous.
Image-only PDFs currently return an explicit error because OCR is not
configured. The sample entities in `pdf_processor.py` are available only when
`process_pdf(..., demo_mode=True)` is explicitly selected. Uploads default to
live mode; multipart field `demo_mode=true` explicitly opts into sample entities
and sample clarification items.

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

## Audit count semantics

- `inventory_rows` counts non-header Excel data rows, including rows with an empty tag.
- `usable_inventory_rows` counts rows with a normalized, non-empty tag.
- `unique_inventory_tags` counts distinct normalized tags and is also returned as the legacy `total_tags` value used for completeness.
- `duplicate_inventory_tags` counts distinct tags repeated in Excel; `duplicate_inventory_rows` counts extra occurrences beyond the first.
- `detected_source_tags` counts distinct PDF tag detections with a valid non-empty source box.
- `matched_tags` and `missing_tags` count inventory audit groups with those statuses. `ambiguous_tags` counts ambiguous inventory groups, including duplicate Excel tags. `pdf_only_tags` counts source detections with no Excel inventory row, which also use `Ambiguous` as their audit-row status. `pending_review_tags` counts pending inventory groups. `audit_rows` is the sum of these five KPI counts.
- Duplicate inventory tags are grouped into one audit row with all originating Excel row numbers and status `Ambiguous`; a single PDF detection is never counted as multiple matches. Both the duplicate tag group count and repeated row count are reported separately.
- PDF-only detections appear once as `Ambiguous` audit rows. They contribute to `audit_rows` and `pdf_only_tags`, but not to inventory status counts or `unique_inventory_tags`.
- `clarification_items` counts only the clarification queue for that run. Fixed sample clarifications are returned only when multipart field `demo_mode=true` is explicitly supplied; live uploads default to no sample clarifications.

Clarification choices are recorded against their processing run. Source-supported
line-crossing clarifications reprocess the saved PDF and regenerate the graph
for the selected junction or crossover interpretation. Other clarification
items without a graph-resolution contract are rejected. An unresolved choice is
saved as unresolved and can be revisited; only a listed option can be recorded.

## Persistent local runs

The backend loads `untangled_backend/.env` at startup with process environment
variables taking precedence. No environment values are returned or logged.

Completed processing runs are stored in SQLite at
`untangled_backend/data/untangle.sqlite3` by default. Set `UNTANGLE_DB_PATH` to
use another local database file. The `processing_runs` table stores run
metadata, the JSON response, and the uploaded PDF/XLSX bytes. The
`clarification_decisions` table stores pending, unresolved, and resolved
decisions scoped by `(run_id, item_id)`. The data directory is ignored by Git.

- `GET /api/runs` lists recent saved runs (`limit` defaults to 20; maximum 100).
- `GET /api/runs/{run_id}` returns the full saved processing result and current
  clarification decisions.
- `GET /api/runs/{run_id}/files/pdf` and `/files/excel` retrieve that run's
  original uploads for local workspace restoration.
- `POST /api/resolve-ambiguity` now requires `run_id` as well as `item_id` and
  `selected_option`, so a choice is never applied to another run.

Authentication is intended for a trusted local demo, not a public deployment.
SQLite persistence does not add OCR: scanned PDFs remain unsupported, and graph
flow direction/topology can remain unverified.

## Local demo authentication

Sign in with `demo@untangle.local` / `untangle-demo-2026`. The backend stores a
salted PBKDF2-HMAC-SHA256 password hash, never the password. Set
`UNTANGLE_DEMO_EMAIL` and `UNTANGLE_DEMO_PASSWORD` before the first backend
start to choose different local demo credentials. These defaults are for a
controlled hackathon demo only; use a unique password on any shared machine.
There is no public registration endpoint.

`POST /api/auth/login` returns a signed bearer token expiring after 12 hours.
The signing key is randomly generated once and stored in the configured SQLite
database. `GET /api/auth/me` validates a restored token. Upload, saved-run
list/retrieval/source-file, and clarification endpoints require authentication
and only operate on the authenticated user's runs.

On startup, the ownership migration adds nullable `owner_id` to existing run
records. Existing rows are preserved with `owner_id = NULL` and hidden from all
accounts; they are not silently assigned to the demo account. This phase has no
owner-claim interface.

## Optional backend AI provider adapters

Gemini, xAI Grok, and Hugging Face Inference Providers have separate backend
adapters in `ai_providers.py`. They use documented REST APIs through `httpx`;
provider credentials are read from this backend directory's `.env` file (or
process environment variables, which take precedence). Keys are never returned
or logged, and no frontend code receives them.

AI provider use defaults to disabled with `AI_PROVIDERS_ENABLED=false`. The
adapters are not called by the upload, extraction, Excel reconciliation,
topology, audit, clarification, or export workflows. If explicitly enabled,
they return provider text as untrusted advisory output; it cannot mark a tag,
connection, or topology as verified. The model IDs in `.env.example` are
starting defaults and still depend on provider account access and availability.

### Windows PowerShell setup

1. Open `untangled_backend/.env` and add the keys to `GEMINI_API_KEY`,
   `XAI_API_KEY`, and/or `HF_TOKEN`. Do not add them to frontend `.env` files
   or commit them. Use an HF token with Inference Providers permission.
2. Keep `AI_PROVIDERS_ENABLED=false` until you intend to make live provider
   requests. To enable adapters locally, set it to `true` in `.env`.
3. From `untangled_backend`, install dependencies with
   `python -m pip install -r requirements.txt`, then run the mocked tests:
   `python -m pytest -q test_provider_diagnostic.py test_ai_providers.py test_pipeline_regressions.py`.
   These tests use `httpx.MockTransport` and do not contact providers.
4. To check exactly one provider after you explicitly choose to enable it,
   temporarily set `AI_PROVIDERS_ENABLED=true` in `untangled_backend/.env`,
   then run only the matching command from PowerShell in `untangled_backend`:

   ```powershell
   python provider_diagnostic.py gemini
   python provider_diagnostic.py xai
   python provider_diagnostic.py huggingface
   python provider_diagnostic.py xai-model
   ```

   Run one command at a time. It sends a short fixed prompt to that provider,
   discards the response text, and prints only success/failure, a sanitized
   error category, and an HTTP status when a response supplied one. For valid
   JSON errors it may also print an allowlisted error code and a fixed generic
   category message. Provider-supplied message text is never returned;
   malformed/unrecognized error bodies yield no provider detail.
   It never prints credentials, authorization headers, prompts, generated text,
   or raw provider responses. Each call is independent of the P&ID pipeline and
   may use provider quota. Restore
   `AI_PROVIDERS_ENABLED=false` in `.env` immediately after the check. The
   diagnostic does not test browser downloads or connect AI to upload/results.
   Mocked tests verify request construction and safe reporting only; a live
   diagnostic is needed to validate a specific credential and model.

An HTTP 400 is classified using a recognized safe error code when present;
otherwise it is `request_rejected`. xAI documents 400 as potentially caused by
an invalid argument or incorrect API key, 401 as authentication, 403 as
permission, 404 as missing model/endpoint, 422 as invalid request fields, and
429 as rate limiting. The diagnostic does not assume a 400 means the key is
invalid. `xai-model` makes one `GET /v1/models` request and reports only whether
the configured model ID (or alias) is listed for the key. The model-list
response is not printed. This makes one additional xAI API request; a listed
model does not guarantee inference access or that a generation request will
succeed.

The Gemini adapter uses `generateContent` and `x-goog-api-key` as documented
by [Google](https://ai.google.dev/gemini-api/docs/generate-content/api-key).
The xAI adapter uses the Responses API with bearer authentication as documented
by [xAI](https://docs.x.ai/developers/rest-api-reference/inference/responses).
The Hugging Face adapter uses its OpenAI-compatible chat endpoint at
`router.huggingface.co/v1/chat/completions`, documented in the
[Inference Providers chat completion guide](https://huggingface.co/docs/inference-providers/en/tasks/chat-completion).

## Setup

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

## Endpoints

- `GET /api/health` — service status and local PyMuPDF text/vector pipeline availability; OCR is not configured
- `POST /api/auth/login` — JSON `{ "email", "password" }` → signed bearer session
- `GET /api/auth/me` — validate bearer session and return its user
- `POST /api/process-pid` — multipart `file_pdf` + `file_excel` → `ProcessPidResponse`
- `POST /api/resolve-ambiguity` — JSON `{ "run_id", "item_id", "selected_option" }` → updated KPIs/edges
- `GET /api/runs` — recent saved-run summaries
- `GET /api/runs/{run_id}` — full saved processing result
- `GET /api/runs/{run_id}/files/{pdf|excel}` — original uploaded file for a saved run
