# UNTANGLE Test Dataset Pack

This folder is intended to be copied/merged into the root of the Project_Untangled workspace. It provides paired PDF + Excel I/O fixtures for repeatable testing and preserves the official Track 1 dataset in its own subfolder.

## Regression fixtures in `test_cases/`

Each numbered case has a matching PDF drawing and `_io.xlsx` inventory:

1. `01_easy_linear` — baseline linear process flow.
2. `02_parallel_pumps` — parallel equipment trains.
3. `03_branch_merge` — branches and merges.
4. `04_control_utility` — process, utility and control/signal separation.
5. `05_dense_recycle` — dense process/recycle structure.
6. `06_scanned_image_only` — scanned/image-only PDF path.
7. `07_missing_ambiguous_tags` — missing and ambiguous tag handling.
8. `08_ambiguous_crossing` — non-connecting crossings versus junction uncertainty.
9. `09_bypass_recycle` — bypass and recycle topology.
10. `10_dense_shared_headers` — dense shared headers.

These are regression fixtures, not official Emerson ground truth. Passing them does not prove accuracy on arbitrary industrial drawings.

## Official Emerson Track 1 dataset

`official_track1/` contains the original files from the uploaded official dataset pack. The primary end-to-end pair is:

- `official_track1/Sample P&IDs_Sanitized 1.pdf`
- `official_track1/UNTANGLE_03_Filtered_IO_Records 1.xlsx`

The `Graphics Screenshots_Sanitized 1.pdf` and `Seal Plan_Sanitized 1.pdf` files are supporting reference material; do not substitute them for the primary P&ID unless the test being performed specifically calls for them. The supplied `README_DATASET.md` is retained unchanged.

## Suggested test sequence

1. Run fixtures 01–05 to validate basic topology and routing.
2. Run fixture 06 to validate scanned-PDF handling and visible OCR failures.
3. Run fixtures 07–10 to validate uncertain tags, crossings, recycle and dense headers.
4. Run the official P&ID PDF with its associated Excel workbook through the live application.
5. Record extraction results, evidence-backed matches, unresolved tags/connections, and any failures. Do not mark a tag matched merely to increase the match count.

## Notes

- Source PDFs and workbooks were copied byte-for-byte from the supplied archives; they were not edited.
- This pack contains test data only, not the application source code or Python/Node dependencies.
- Keep generated reports and output diagrams outside this source dataset folder.
