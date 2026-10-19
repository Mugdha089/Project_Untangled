# Project UNTANGLE — Diverse Synthetic P&ID Test Pack

## Purpose
These fixtures supplement the user's two web-sourced examples. They are synthetic engineering-style diagrams made for software testing only, not for plant operation, construction, or safety decisions.

## Files
Each numbered case includes:
- `.pdf`: P&ID source diagram
- `_io.xlsx`: matching workbook with Instrument Tag List, Major Equipment, and Expected Connections sheets

## Test cases
1. **01_easy_linear** — straight-through flow with tank, pump, filter, flow valve, vessel, PT/FT/LT.
2. **02_parallel_pumps** — duty/standby parallel pumps with two branches joining a common downstream path.
3. **03_branch_merge** — a feed splits at J1 through heater/cooler branches and merges at J2 before a separator.
4. **04_control_utility** — process flow plus a steam utility line and dashed controller-to-valve signal. Utility and signal must not become process-flow edges.
5. **05_dense_recycle** — parallel pumps, heater, separator, outlet valve, recycle return, instruments, and control signal.
6. **06_scanned_image_only** — image-only PDF based on the branch/merge diagram; no selectable/searchable embedded text. Tests OCR fallback.
7. **07_missing_ambiguous_tags** — known tags plus deliberately absent near-match and unrelated tags in Excel. Missing tags must remain missing and must not be auto-corrected to visible tags.
8. **08_ambiguous_crossing** — two independently connected process routes cross geometrically. The workbook records the expected equipment/tags and both allowed interpretations; a live run must show a crop and preserve separate routes until reviewed.
9. **09_bypass_recycle** — an exchanger bypass and a return loop from the downstream vessel to pump suction, with instrument tags and one absent inventory tag.
10. **10_dense_shared_headers** — parallel pumps, two treatment branches, shared suction/discharge headers, and dense instrumentation with one absent inventory tag.

## Ground truth / acceptance notes
- Equipment and instrument tags are recorded in each workbook.
- The `Expected Connections` sheet describes expected high-level topology. These are semantic expected connections; the app may represent junction nodes explicitly, so compare equivalent paths rather than requiring identical internal graph node counts.
- `process-flow`, `branch`, `merge`, and `recycle` represent process topology.
- `utility` is a separate utility connection, not a process-flow edge.
- `instrument-signal` is a signal relationship, not a process-flow edge.
- For Case 7, `LT-609`, `FT-601A`, `PT-699`, and equipment `E-609` are deliberately absent. They must not be marked as confirmed matches.
- Case 8 has no flow arrows. Its two visible routes are `P-801`→`V-801` and `E-801`→`TK-801`; those paths remain separate for the crossover choice and become connected through a source-local junction only after the user selects the junction interpretation.
- Cases 9 and 10 have ground-truth equipment, tag, and high-level topology rows in their workbooks. The listed `LT-999` and `LT-1099` tags are intentionally absent and must remain missing.
- Synthetic fixture ground truth describes expected behavior. Regression results must be reported separately; the workbook is not evidence that the pipeline actually met the expectation.
- Case 6 should have zero embedded text characters before OCR; the app should identify it as image-only and attempt OCR or clearly report OCR unavailability.

## Important limitations
These are controlled synthetic fixtures. They test layout diversity and known edge cases, but do not represent all international P&ID symbol standards, poor scans, rotated drawings, overlapping labels, unusual line types, or plant-specific conventions. Add more real-world examples before making broad reliability claims.

## Suggested scorecard
For each case, record:
1. PDF extraction mode: native text / OCR / failure
2. Instrument tags: true positives, false positives, false negatives
3. Equipment tags: true positives, false positives, false negatives
4. Topology: correct process edges, missing edges, invented edges
5. Branch/merge/recycle preservation
6. Utility/signal separation
7. Simplified diagram generated and readable
8. Honest warning states for unsupported or ambiguous features
9. Export works and output opens
10. Browser Console and Network errors

Do not treat successful API responses or a high graph-integrity percentage as evidence of correct topology unless the graph is checked against source evidence.

## Current extraction behavior and root causes

- Equipment labels are detected from embedded text tags. Prefix-only classification covers a limited set; an unfamiliar tag is promoted to equipment only when a nearby explicit equipment descriptor supports its type. Untagged vector symbols are not classified as equipment.
- Process-line extraction accepts legend-classified PyMuPDF line items (`l`). Other path commands and image-only strokes are not treated as process pipes.
- The prior point-on-segment check compared a distance tolerance directly to a normalized segment fraction. On a long line that allowed points far beyond the endpoint to count as lying on the line. The graph also kept nearby line endpoints as separate vertices. The check now converts the tolerance to a fraction of segment length, and endpoints snap only within `clamp(0.001 × page diagonal, 0.5 pt, 2 pt)`; a cluster's every pair must remain within tolerance to avoid transitive over-joining.
- Graph edges include IDs of supporting vector line items. The previous fixed edge confidence of `0.85` was uncalibrated and is no longer emitted. Edges created through a selected junction are marked `user_confirmed_crossing`.
- A document with embedded title text but no detectable tag or equipment labels is now rejected with an OCR/image-extraction limitation instead of returning an apparently processed empty audit.
- These are code-level root causes and targeted regressions, not measured fixture accuracy. Run `python -m pytest -q test_pipeline_regressions.py` from `untangled_backend` before making accuracy claims.
