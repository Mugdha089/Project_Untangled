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

## Ground truth / acceptance notes
- Equipment and instrument tags are recorded in each workbook.
- The `Expected Connections` sheet describes expected high-level topology. These are semantic expected connections; the app may represent junction nodes explicitly, so compare equivalent paths rather than requiring identical internal graph node counts.
- `process-flow`, `branch`, `merge`, and `recycle` represent process topology.
- `utility` is a separate utility connection, not a process-flow edge.
- `instrument-signal` is a signal relationship, not a process-flow edge.
- For Case 7, `LT-609`, `FT-601A`, `PT-699`, and equipment `E-609` are deliberately absent. They must not be marked as confirmed matches.
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
