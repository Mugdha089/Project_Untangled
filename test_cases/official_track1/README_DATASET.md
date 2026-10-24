UNTANGLE Track 1 official dataset subset

This archive contains ONLY the Project Untangle folder from the Emerson Track 1 dataset bundle. It intentionally excludes the other problem statements and other Track 1 projects.

Files:
- Sample P&IDs_Sanitized 1.pdf: 4 pages of P&ID drawings. The PDF has no extractable text layer in the current inspection, so it requires image-based processing/OCR for text labels. Treat this as the primary diagram regression corpus. Verify exact page-to-P&ID mapping from title blocks/source evidence rather than guessing.
- UNTANGLE_03_Filtered_IO_Records 1.xlsx: 7 sheets (Legend, Filtered IO, Summary, Closed Drain, Oily Water, Diesel Fuel, Potable Water). Summary reports 271 records across four P&ID references and 28 source columns. Its scope note explicitly says it includes physical I/O and relevant DCS software/derived records. Do not assume every inventory row must appear as a physical symbol on a P&ID; distinguish field/valve/equipment-visible records from software-derived DCS records before labeling them missing.
- Graphics Screenshots_Sanitized 1.pdf: 8 pages of edit/runtime control-system graphic screenshots. Use as supplementary context for tag/display relationships; do not treat as the primary P&ID drawing set without verifying relevance.
- Seal Plan_Sanitized 1.pdf: 1 page containing a dense table and seal-plan drawings. Supplementary reference; do not conflate it with P&ID topology.

Suggested workspace location: test_cases/official_track1/
Preserve these originals unchanged. Use them for read-only regression evaluation. Do not hardcode expected outputs from these files into live processing.
