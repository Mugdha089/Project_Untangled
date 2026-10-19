"""Excel I/O tag normalization and matching engine for Project UNTANGLE."""

from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

TAG_HEADER_CANDIDATES: Tuple[str, ...] = (
    "tag",
    "instrument tag",
    "tag number",
    "i/o tag",
    "io tag",
    "tag no",
    "tag no.",
    "instrument",
    "loop tag",
    "equipment tag",
)

TYPE_HEADER_CANDIDATES: Tuple[str, ...] = (
    "type",
    "instrument type",
    "description",
    "desc",
    "function",
    "signal type",
)

TAG_PATTERN = re.compile(
    r"^[A-Z]{1,4}-?\d{1,4}(?:-\d{2,4})?[A-Z]?$",
    re.IGNORECASE,
)


class ExcelParseError(Exception):
    """Raised when an Excel workbook cannot be parsed into a tag inventory."""


def _normalize_header(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _normalize_tag(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = re.sub(r"\s+", "", str(value).strip().upper())
    # Canonicalise PT 101 / PT_101 → PT-101 when a digit block follows letters.
    match = re.match(
        r"^([A-Z]{1,4})[-_]?(\d{1,4}(?:-\d{2,4})?[A-Z]?)$",
        text,
    )
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return text


def _find_column(columns: List[str], candidates: Tuple[str, ...]) -> Optional[str]:
    normalized = {_normalize_header(col): col for col in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    # Partial / contains match as fallback.
    for candidate in candidates:
        for norm, original in normalized.items():
            if candidate in norm:
                return original
    return None


def _infer_tag_type(tag: str) -> str:
    prefix = tag.split("-")[0] if "-" in tag else tag[:2]
    mapping = {
        "PT": "Pressure Transmitter",
        "FT": "Flow Transmitter",
        "LT": "Level Transmitter",
        "TT": "Temperature Transmitter",
        "LV": "Level Valve",
        "FV": "Flow Valve",
        "XV": "Solenoid Valve",
        "PV": "Pressure Valve",
        "PI": "Pressure Indicator",
        "FI": "Flow Indicator",
        "LI": "Level Indicator",
        "TI": "Temperature Indicator",
        "PC": "Pressure Controller",
        "FC": "Flow Controller",
        "LC": "Level Controller",
        "TC": "Temperature Controller",
    }
    return mapping.get(prefix, "Instrument")


def load_excel_tags(file_bytes: bytes, filename: str = "io_list.xlsx") -> Dict[str, Any]:
    """
    Load an .xlsx I/O list and return a normalised tag inventory.

    Returns
    -------
    dict with keys:
        tags: List[Dict] — normalised rows
        tag_column: str
        type_column: Optional[str]
        duplicates: List[str]
        empty_rows: List[int]
        total_rows: int
    """
    if not file_bytes:
        raise ExcelParseError("Excel file is empty.")

    try:
        buffer = io.BytesIO(file_bytes)
        # Try openpyxl first; fall back to default engine discovery.
        try:
            workbook = pd.ExcelFile(buffer, engine="openpyxl")
        except Exception:
            buffer.seek(0)
            workbook = pd.ExcelFile(buffer)
        sheet_name = workbook.sheet_names[0]
        df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    except Exception as exc:
        logger.exception("Failed to read Excel file '%s'", filename)
        raise ExcelParseError(f"Unable to read Excel file '{filename}': {exc}") from exc

    if df.empty:
        raise ExcelParseError("Excel workbook contains no data rows.")

    columns = [str(c) for c in df.columns.tolist()]
    tag_column = _find_column(columns, TAG_HEADER_CANDIDATES)
    type_column = _find_column(columns, TYPE_HEADER_CANDIDATES)

    if tag_column is None:
        # Heuristic: pick the first column whose values look like tags.
        for col in columns:
            sample = df[col].dropna().astype(str).head(20)
            hits = sum(1 for v in sample if TAG_PATTERN.match(_normalize_tag(v)))
            if hits >= max(2, len(sample) // 3):
                tag_column = col
                break

    if tag_column is None:
        raise ExcelParseError(
            "Could not detect a tag column. Expected headers such as "
            "'Tag', 'Instrument Tag', 'Tag Number', or 'I/O Tag'."
        )

    logger.info(
        "Detected tag column='%s' type_column='%s' sheet='%s' rows=%d",
        tag_column,
        type_column,
        sheet_name,
        len(df),
    )

    tags: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    duplicates: List[str] = []
    empty_rows: List[int] = []

    for idx, row in df.iterrows():
        excel_row = int(idx) + 2  # header is row 1 in Excel
        raw_tag = row.get(tag_column)
        tag = _normalize_tag(raw_tag)

        if not tag:
            empty_rows.append(excel_row)
            continue

        raw_type = ""
        if type_column is not None:
            type_val = row.get(type_column)
            if type_val is not None and not (isinstance(type_val, float) and pd.isna(type_val)):
                raw_type = str(type_val).strip()

        instrument_type = raw_type or _infer_tag_type(tag)

        if tag in seen:
            duplicates.append(tag)
            status_note = "duplicate"
        else:
            seen[tag] = excel_row
            status_note = "unique"

        tags.append(
            {
                "tag_name": tag,
                "original_tag": str(raw_tag).strip() if raw_tag is not None else tag,
                "type": instrument_type,
                "excel_row": excel_row,
                "status_note": status_note,
            }
        )

    additional_rows = 0
    parsed_equipment_sheets: List[str] = []
    for equipment_sheet in workbook.sheet_names:
        if equipment_sheet == sheet_name or "major equipment" not in _normalize_header(equipment_sheet):
            continue
        equipment_df = pd.read_excel(workbook, sheet_name=equipment_sheet, dtype=object)
        if equipment_df.empty:
            continue
        additional_rows += len(equipment_df)
        equipment_columns = [str(column) for column in equipment_df.columns.tolist()]
        equipment_tag_column = _find_column(equipment_columns, TAG_HEADER_CANDIDATES)
        if equipment_tag_column is None:
            continue
        equipment_type_column = _find_column(equipment_columns, TYPE_HEADER_CANDIDATES)
        parsed_equipment_sheets.append(equipment_sheet)
        for idx, row in equipment_df.iterrows():
            excel_row = int(idx) + 2
            raw_tag = row.get(equipment_tag_column)
            tag = _normalize_tag(raw_tag)
            if not tag:
                empty_rows.append(excel_row)
                continue
            raw_type = row.get(equipment_type_column) if equipment_type_column else None
            instrument_type = (
                str(raw_type).strip()
                if raw_type is not None and not (isinstance(raw_type, float) and pd.isna(raw_type))
                else _infer_tag_type(tag)
            )
            duplicate = tag in seen
            if duplicate:
                duplicates.append(tag)
            else:
                seen[tag] = excel_row
            tags.append(
                {
                    "tag_name": tag,
                    "original_tag": str(raw_tag).strip() if raw_tag is not None else tag,
                    "type": instrument_type,
                    "excel_row": excel_row,
                    "excel_sheet": equipment_sheet,
                    "status_note": "duplicate" if duplicate else "unique",
                }
            )

    logger.info(
        "Parsed %d tags (%d duplicates, %d empty rows) from '%s'",
        len(tags),
        len(duplicates),
        len(empty_rows),
        filename,
    )

    return {
        "tags": tags,
        "tag_column": tag_column,
        "type_column": type_column,
        "duplicates": duplicates,
        "empty_rows": empty_rows,
        "total_rows": len(df) + additional_rows,
        "sheet_name": sheet_name,
        "sheet_names": [sheet_name, *parsed_equipment_sheets],
    }


def build_fallback_inventory() -> Dict[str, Any]:
    """Sample I/O inventory used when Excel parsing yields no usable tags."""
    sample = [
        ("PT-101", "Pressure Transmitter", 14),
        ("FT-101", "Flow Transmitter", 15),
        ("LV-102", "Level Valve", 16),
        ("FT-202", "Flow Transmitter", 22),
        ("LT-309", "Level Transmitter", 88),
        ("XV-104", "Solenoid Valve", 102),
        ("TT-110", "Temperature Transmitter", 30),
        ("PC-101", "Pressure Controller", 31),
    ]

    tags = [
        {
            "tag_name": tag,
            "original_tag": tag,
            "type": typ,
            "excel_row": row,
            "status_note": "unique",
        }
        for tag, typ, row in sample
    ]
    return {
        "tags": tags,
        "tag_column": "Tag",
        "type_column": "Type",
        "duplicates": [],
        "empty_rows": [],
        "total_rows": len(tags),
        "sheet_name": "fallback",
    }
