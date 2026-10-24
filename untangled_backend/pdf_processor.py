"""PDF rendering, text/bbox extraction, and tag–equipment mapping for UNTANGLE."""

from __future__ import annotations

import base64
import csv
import io
import logging
import math
import os
import re
import shutil
import subprocess
from numbers import Real
from typing import Any, Dict, List, Optional, Tuple

from topology_evidence import (
    CONNECTED_JUNCTION,
    CROSSOVER,
    UNRESOLVED,
    find_ambiguous_process_crossings,
    find_equipment_nozzle_endpoints,
)
from raster_linework import extract_raster_linework

logger = logging.getLogger(__name__)

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:  # pragma: no cover - optional at import time for CI stubs
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None  # type: ignore

TAG_RE = re.compile(
    r"\b((?:\d{1,4}[-\s_]+)?[A-Z]{1,4})[-\s_]?(\d{1,4}(?:-\d{2,4})?[A-Z]?)\b",
    re.IGNORECASE,
)

EQUIPMENT_RE = re.compile(
    r"\b((?:\d{1,4}[-\s_]+)?(?:FCV|TK|HX|FV|LV|XV|PV|HV|T|P|M|R|E|V|F))[-\s_]?(\d{2,4}[A-Z]?)\b",
    re.IGNORECASE,
)
OCR_RENDER_SCALE = 6.0
OCR_MIN_CONFIDENCE = 80.0
MAX_CLARIFICATIONS_PER_RUN = 3
INSTRUMENT_PREFIXES = {
    "PT", "FT", "LT", "TT", "PI", "FI", "LI", "TI",
    "PC", "FC", "LC", "TC", "PIC", "FIC", "LIC", "TIC",
}

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

class PdfProcessError(Exception):
    """Raised when a PDF cannot be opened or processed."""


def find_tesseract_executable() -> Optional[str]:
    """Find Tesseract on PATH or at its standard Windows install location."""
    executable = shutil.which("tesseract")
    if executable:
        return executable
    if os.name != "nt":
        return None

    install_roots = (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    )
    for root in install_roots:
        candidate = os.path.join(root, "Tesseract-OCR", "tesseract.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def _bbox_to_ints(bbox: Tuple[float, float, float, float]) -> List[int]:
    return [int(round(v)) for v in bbox]


def _canonical_tag(prefix: str, number: str) -> str:
    normalized_prefix = prefix.upper().strip()
    unit_prefix = re.fullmatch(r"(\d{1,4})[-\s_]+([A-Z]{1,4})", normalized_prefix)
    if unit_prefix:
        normalized_prefix = f"{unit_prefix.group(1)}-{unit_prefix.group(2)}"
    else:
        normalized_prefix = re.sub(r"[\s_]+", "", normalized_prefix)
    return f"{normalized_prefix}-{number.upper()}"


def _prefix_without_unit(prefix: str) -> str:
    unit_prefix = re.fullmatch(r"\d{1,4}[-\s_]+([A-Z]{1,4})", prefix, re.IGNORECASE)
    return unit_prefix.group(1).upper() if unit_prefix else prefix.upper()


def _extract_embedded_text(
    doc: Any,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, bool]:
    """Extract tags and equipment candidates from embedded PDF text blocks."""
    tags: List[Dict[str, Any]] = []
    equipment: List[Dict[str, Any]] = []
    seen_tags: set = set()
    seen_eq: set = set()
    has_embedded_text = False

    for page_index in range(len(doc)):
        page = doc[page_index]
        shape_bounds = _page_shape_bounds(page)
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
                has_embedded_text = True
                # Aggregate span bbox.
                xs1, ys1, xs2, ys2 = [], [], [], []
                for span in spans:
                    bx = span.get("bbox", (0, 0, 0, 0))
                    xs1.append(bx[0])
                    ys1.append(bx[1])
                    xs2.append(bx[2])
                    ys2.append(bx[3])
                bbox = _bbox_to_ints((min(xs1), min(ys1), max(xs2), max(ys2)))

                # Restrict detections to tag-like text lines. This prevents tags
                # quoted in captions or explanatory notes from becoming evidence.
                tag_match = TAG_RE.fullmatch(text)
                if tag_match is None:
                    continue

                equipment_type = None
                equipment_match = EQUIPMENT_RE.fullmatch(text)
                prefix = _prefix_without_unit(tag_match.group(1))
                if equipment_match is not None:
                    prefix = _prefix_without_unit(equipment_match.group(1))
                    equipment_type = _equipment_type_from_prefix(prefix)
                has_unit_prefix = bool(
                    re.match(r"^\d{1,4}[-\s_]+", tag_match.group(1))
                )
                if (
                    equipment_type is None
                    and prefix not in INSTRUMENT_PREFIXES
                    and not has_unit_prefix
                ):
                    equipment_type = _equipment_type_from_context(
                        prefix,
                        bbox,
                        blocks,
                        shape_bounds,
                    )

                tag = _canonical_tag(tag_match.group(1), tag_match.group(2))
                if equipment_type is not None:
                    equipment_prefix = prefix
                    number = tag_match.group(2).upper()
                    tag = f"{equipment_prefix}-{number}"
                    if tag not in seen_eq:
                        seen_eq.add(tag)
                        equipment.append(
                            {
                                "id": f"eq_{tag.lower().replace('-', '')}",
                                "tag": tag,
                                "type": equipment_type,
                                "label": f"{equipment_type.title()} {tag}",
                                "source_bbox": bbox,
                                "source_page": page_index,
                                "source_symbol_bbox": _nearest_shape_bbox(
                                    bbox, shape_bounds
                                ),
                                "confidence": 0.90,
                                "page": page_index,
                                "raw_text": text,
                            }
                        )
                    continue

                for match in [tag_match]:
                    tag = _canonical_tag(match.group(1), match.group(2))
                    if tag in seen_tags:
                        continue
                    seen_tags.add(tag)
                    tags.append(
                        {
                            "tag_name": tag,
                            "type": _infer_instrument_type(tag),
                            "source_bbox": bbox,
                            "source_page": page_index,
                            "confidence": 0.92,
                            "page": page_index,
                            "parent_equipment": None,
                            "raw_text": text,
                        }
                    )

    return tags, equipment, len(doc), has_embedded_text


def _page_shape_bounds(page: Any) -> List[Tuple[float, float, float, float]]:
    """Return non-line vector bounds suitable for nearby symbol evidence."""
    shapes = []
    for drawing in page.get_drawings():
        items = drawing.get("items", [])
        if not items:
            continue
        rect = drawing.get("rect")
        if rect is None:
            continue
        x1, y1, x2, y2 = (float(value) for value in rect)
        width, height = x2 - x1, y2 - y1
        if (
            8 <= width <= 150
            and 8 <= height <= 150
            and max(width / height, height / width) <= 2.5
        ):
            shapes.append((x1, y1, x2, y2))
    return shapes


def _bbox_gap(
    first: Tuple[float, float, float, float],
    second: Tuple[float, float, float, float],
) -> float:
    dx = max(first[0] - second[2], second[0] - first[2], 0.0)
    dy = max(first[1] - second[3], second[1] - first[3], 0.0)
    return math.hypot(dx, dy)


def _nearest_shape_bbox(
    bbox: List[int],
    shapes: List[Tuple[float, float, float, float]],
) -> Optional[List[int]]:
    text_box = tuple(float(value) for value in bbox)
    candidates = [
        shape
        for shape in shapes
        if 8 <= shape[2] - shape[0] <= 150 and 8 <= shape[3] - shape[1] <= 150
    ]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda shape: _bbox_gap(text_box, shape))
    if _bbox_gap(text_box, nearest) > 55:
        return None

    # A single equipment symbol may be composed of several overlapping PDF
    # paths (for example a vessel body and its top/bottom ellipses). Retain the
    # connected union so nozzle geometry is measured against the full symbol,
    # not whichever sub-path happens to be nearest the tag text.
    group = [nearest]
    remaining = [shape for shape in candidates if shape != nearest]
    while True:
        expanded = []
        for shape in remaining:
            overlaps_group = any(
                max(shape[0], member[0]) <= min(shape[2], member[2])
                and max(shape[1], member[1]) <= min(shape[3], member[3])
                for member in group
            )
            group_bounds = (
                min([shape[0], *(member[0] for member in group)]),
                min([shape[1], *(member[1] for member in group)]),
                max([shape[2], *(member[2] for member in group)]),
                max([shape[3], *(member[3] for member in group)]),
            )
            if (
                overlaps_group
                and group_bounds[2] - group_bounds[0] <= 150
                and group_bounds[3] - group_bounds[1] <= 150
            ):
                expanded.append(shape)
        if not expanded:
            break
        group.extend(expanded)
        remaining = [shape for shape in remaining if shape not in expanded]
    return _bbox_to_ints(
        (
            min(shape[0] for shape in group),
            min(shape[1] for shape in group),
            max(shape[2] for shape in group),
            max(shape[3] for shape in group),
        )
    )


def _equipment_type_from_context(
    prefix: str,
    bbox: List[int],
    blocks: List[Dict[str, Any]],
    shapes: List[Tuple[float, float, float, float]],
) -> Optional[str]:
    """Use nearby PDF labels and vector symbols to disambiguate equipment tags."""
    text_box = tuple(float(value) for value in bbox)
    nearby_text: List[Tuple[float, str]] = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_text = "".join(
                span.get("text", "") for span in line.get("spans", [])
            ).strip()
            if not line_text or TAG_RE.fullmatch(line_text):
                continue
            line_bbox = tuple(
                float(value)
                for value in line.get("spans", [])[0].get("bbox", (0, 0, 0, 0))
            )
            # Equipment descriptors are often placed below the symbol while
            # the tag is above it. The 80-point cap still uses nearest geometry
            # and avoids importing unrelated title-block/caption text.
            if _bbox_gap(text_box, line_bbox) <= 80:
                nearby_text.append((_bbox_gap(text_box, line_bbox), line_text.lower()))

    nearby_text.sort(key=lambda item: item[0])
    description = " ".join(text for _, text in nearby_text)
    if prefix == "F":
        if "filter" in description:
            return "filter"
        if any(term in description for term in ("vessel", "separator", "drum")):
            return "vessel"
        return None
    if prefix in {"FCV", "FV", "LV", "XV", "PV", "HV"}:
        if "valve" in description:
            return "valve"
        symbol = _nearest_shape_bbox(bbox, shapes)
        if symbol is not None:
            width = symbol[2] - symbol[0]
            height = symbol[3] - symbol[1]
            if 8 <= width <= 45 and 8 <= height <= 40:
                return "valve"
        return None
    descriptor_types = (
        (("heat exchanger", "exchanger"), "exchanger"),
        (("pump",), "pump"),
        (("tank",), "tank"),
        (("mixer", "agitator"), "mixer"),
        (("vessel", "separator", "drum", "reactor", "column"), "vessel"),
        (("filter",), "filter"),
    )
    for _, nearby_label in nearby_text:
        for descriptors, equipment_type in descriptor_types:
            if any(descriptor in nearby_label for descriptor in descriptors):
                return equipment_type
    return None


def _infer_instrument_type(tag: str) -> str:
    prefix_match = re.match(r"^(?:\d{1,4}-)?([A-Z]{1,4})-", tag, re.IGNORECASE)
    prefix = prefix_match.group(1).upper() if prefix_match else tag.split("-")[0]
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
    prefix = _prefix_without_unit(prefix)
    mapping = {
        "TK": "tank",
        "T": "tank",
        "P": "pump",
        "M": "mixer",
        "R": "vessel",
        "E": "exchanger",
        "V": "vessel",
        "HX": "exchanger",
    }
    return mapping.get(prefix)


def _drawing_style_key(drawing: Dict[str, Any]) -> Tuple[Any, ...]:
    color = drawing.get("color")
    normalized_color = (
        tuple(round(float(value), 3) for value in color)
        if color is not None
        else None
    )
    return (
        normalized_color,
        str(drawing.get("dashes") or "").strip(),
        round(float(drawing.get("width") or 0.0), 3),
    )


def _extract_drawing_evidence(doc: Any) -> Dict[str, Any]:
    """Classify vector line styles from nearby drawing-legend labels.

    Engineering drawings place legend swatches on either side of their text.
    Associate the nearest aligned horizontal stroke from either side so a
    valid process-line style is not discarded solely because the legend's
    layout differs from the older left-swatch fixtures.
    """
    segments: List[Dict[str, Any]] = []
    page_bounds: Dict[str, List[float]] = {}

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_rect = page.rect
        page_bounds[str(page_index)] = [
            float(page_rect.x0),
            float(page_rect.y0),
            float(page_rect.x1),
            float(page_rect.y1),
        ]
        drawings = page.get_drawings()
        legend_styles: Dict[Tuple[Any, ...], str] = {}
        legend_strokes: set = set()
        text_lines = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(span.get("text", "") for span in spans).strip()
                if text and spans:
                    text_lines.append(
                        (
                            text.lower(),
                            tuple(float(value) for value in spans[0]["bbox"]),
                        )
                    )

        for label, label_bbox in text_lines:
            if "utility" in label and "line" in label:
                kind = "utility"
            elif "signal" in label and "instrument" in label:
                kind = "instrument_signal"
            elif "process" in label and ("line" in label or "pipe" in label):
                kind = "process"
            else:
                continue

            candidates = []
            label_y = (label_bbox[1] + label_bbox[3]) / 2
            for drawing_index, drawing in enumerate(drawings):
                for item_index, item in enumerate(drawing.get("items", [])):
                    if item[0] != "l":
                        continue
                    start = tuple(float(value) for value in item[1])
                    end = tuple(float(value) for value in item[2])
                    if abs(start[1] - end[1]) > 1.5:
                        continue
                    left, right = sorted((start[0], end[0]))
                    if right <= label_bbox[0]:
                        gap = label_bbox[0] - right
                    elif left >= label_bbox[2]:
                        gap = left - label_bbox[2]
                    else:
                        gap = 0.0
                    y_gap = abs((start[1] + end[1]) / 2 - label_y)
                    if -2 <= gap <= 25 and y_gap <= 6 and right - left >= 12:
                        candidates.append(
                            (
                                gap + y_gap,
                                _drawing_style_key(drawing),
                                drawing_index,
                                item_index,
                            )
                        )
            if candidates:
                _, key, legend_drawing, legend_item = min(
                    candidates, key=lambda candidate: candidate[0]
                )
                legend_strokes.add((legend_drawing, legend_item))
                previous = legend_styles.get(key)
                legend_styles[key] = kind if previous in (None, kind) else "ambiguous"

        signal_dash_patterns = {
            k[1]
            for k, v in legend_styles.items()
            if v == "instrument_signal" and k[1] not in ("", "[] 0")
        }

        for drawing_index, drawing in enumerate(drawings):
            style_key = _drawing_style_key(drawing)
            kind = legend_styles.get(style_key)
            if kind is None and (
                style_key[1] in signal_dash_patterns
                or (signal_dash_patterns and style_key[1] not in ("", "[] 0"))
            ):
                kind = "instrument_signal"
            if kind is None or kind == "ambiguous":
                continue
            for item_index, item in enumerate(drawing.get("items", [])):
                if item[0] != "l":
                    continue
                if (drawing_index, item_index) in legend_strokes:
                    continue
                start = tuple(float(value) for value in item[1])
                end = tuple(float(value) for value in item[2])
                if math.dist(start, end) < 4:
                    continue
                segments.append(
                    {
                        "id": f"p{page_index}_d{drawing_index}_i{item_index}",
                        "page": page_index,
                        "start": [round(start[0], 3), round(start[1], 3)],
                        "end": [round(end[0], 3), round(end[1], 3)],
                        "kind": kind,
                        "source_bbox": _bbox_to_ints(
                            (
                                min(start[0], end[0]),
                                min(start[1], end[1]),
                                max(start[0], end[0]),
                                max(start[1], end[1]),
                            )
                        ),
                    }
                )

    return {
        "segments": segments,
        "page_bounds": page_bounds,
        "classified_process_lines": sum(
            1 for segment in segments if segment["kind"] == "process"
        ),
    }


def _extract_ocr_labels(
    page: Any,
    page_index: int,
    executable: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run local Tesseract TSV OCR and retain source-page evidence for labels."""
    executable = executable or find_tesseract_executable()
    if executable is None:
        raise PdfProcessError(
            "OCR is not configured because local Tesseract was not found. "
            "Install Tesseract OCR in Windows PowerShell with "
            "`winget install --id UB-Mannheim.TesseractOCR -e`. If the installer "
            "does not add it to PATH, run `$env:Path += "
            "\";C:\\Program Files\\Tesseract-OCR\"` in the backend terminal "
            "(or add that folder to the Windows user PATH), verify with "
            "`tesseract --version`, and restart the backend. Scanned drawing "
            "labels cannot be verified without it."
        )

    image = page.get_pixmap(
        matrix=fitz.Matrix(OCR_RENDER_SCALE, OCR_RENDER_SCALE),
        alpha=False,
    ).tobytes("png")
    try:
        result = subprocess.run(
            [executable, "stdin", "stdout", "tsv", "--psm", "11"],
            input=image,
            capture_output=True,
            check=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise PdfProcessError(
            "The configured Tesseract OCR executable could not be started. "
            "Install Tesseract OCR and ensure its executable is on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PdfProcessError(
            f"Local Tesseract OCR timed out on PDF page {page_index + 1}."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        message = f"Local Tesseract OCR failed on PDF page {page_index + 1}."
        if detail:
            message += f" {detail}"
        raise PdfProcessError(message) from exc

    text = result.stdout.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    lines: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in reader:
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        left = int(row["left"])
        top = int(row["top"])
        width = int(row["width"])
        height = int(row["height"])
        line = lines.setdefault(
            key,
            {
                "words": [],
                "confidences": [],
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
            },
        )
        line["words"].append(row["text"].strip())
        line["left"] = min(line["left"], left)
        line["top"] = min(line["top"], top)
        line["right"] = max(line["right"], left + width)
        line["bottom"] = max(line["bottom"], top + height)
        try:
            confidence = float(row["conf"])
        except (KeyError, ValueError):
            continue
        if math.isfinite(confidence) and 0 <= confidence <= 100:
            line["confidences"].append(confidence)

    tags: List[Dict[str, Any]] = []
    equipment: List[Dict[str, Any]] = []
    for line in lines.values():
        raw_text = " ".join(line["words"]).strip()
        tag_match = TAG_RE.fullmatch(raw_text)
        if tag_match is None:
            continue

        bbox = _bbox_to_ints(
            (
                line["left"] / OCR_RENDER_SCALE,
                line["top"] / OCR_RENDER_SCALE,
                line["right"] / OCR_RENDER_SCALE,
                line["bottom"] / OCR_RENDER_SCALE,
            )
        )
        ocr_confidence = (
            sum(line["confidences"]) / len(line["confidences"])
            if line["confidences"]
            else None
        )
        confidence = ocr_confidence / 100 if ocr_confidence is not None else 0.0
        uncertain = ocr_confidence is None or ocr_confidence < OCR_MIN_CONFIDENCE
        equipment_match = EQUIPMENT_RE.fullmatch(raw_text)
        prefix = _prefix_without_unit(tag_match.group(1))
        equipment_type = None
        if equipment_match is not None:
            prefix = _prefix_without_unit(equipment_match.group(1))
            equipment_type = _equipment_type_from_prefix(prefix)

        canonical_tag = _canonical_tag(tag_match.group(1), tag_match.group(2))
        common = {
            "source_bbox": bbox,
            "source_page": page_index,
            "confidence": confidence,
            "page": page_index,
            "raw_text": raw_text,
            "ocr_confidence": ocr_confidence,
            "ambiguous": uncertain,
            "ambiguity_reason": "low_ocr_confidence" if uncertain else None,
        }
        if equipment_type is not None:
            equipment.append(
                {
                    "id": f"eq_{canonical_tag.lower().replace('-', '')}",
                    "tag": canonical_tag,
                    "type": equipment_type,
                    "label": f"{equipment_type.title()} {canonical_tag}",
                    "source_symbol_bbox": None,
                    **common,
                }
            )
            continue

        tags.append(
            {
                "tag_name": canonical_tag,
                "type": _infer_instrument_type(canonical_tag),
                "parent_equipment": None,
                **common,
            }
        )

    return tags, equipment


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


def match_excel_inventory(
    pdf_tags: List[Dict[str, Any]],
    excel_tags: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Reconcile PDF detections against the Excel I/O inventory.

    Matches unique inventory tags only. Repeated inventory rows are grouped and
    marked ambiguous; absent records are marked missing only when their
    physical visibility and referenced drawing scope can be evaluated.
    PDF-only detections remain visible as ambiguous rows.
    """
    pdf_index = {t["tag_name"]: t for t in pdf_tags}
    audit: List[Dict[str, Any]] = []
    inventory_by_name: Dict[str, List[Dict[str, Any]]] = {}

    for excel_row in excel_tags:
        inventory_by_name.setdefault(excel_row["tag_name"], []).append(excel_row)

    for name, inventory_rows in inventory_by_name.items():
        excel_row = inventory_rows[0]
        detected = pdf_index.get(name)
        bbox = detected.get("source_bbox") if detected else None
        valid_bbox = has_valid_source_bbox(bbox)
        source_text = detected.get("raw_text") if detected else None
        ocr_confidence = detected.get("ocr_confidence") if detected else None
        duplicate_rows = len(inventory_rows) > 1
        detected_as_ambiguous = bool(
            detected and detected.get("ambiguous") and valid_bbox
        )

        if duplicate_rows or detected_as_ambiguous:
            status = "Ambiguous"
            reason = (
                "duplicate_inventory_tag"
                if duplicate_rows
                else detected.get("ambiguity_reason") or "ambiguous_pdf_detection"
            )
            audit.append(
                {
                    "tag_name": name,
                    "type": excel_row.get("type", "Instrument"),
                    "source_bbox": list(bbox) if valid_bbox else [0, 0, 0, 0],
                    "excel_row": excel_row["excel_row"],
                    "excel_rows": [int(row["excel_row"]) for row in inventory_rows],
                    "excel_sheet": excel_row.get("excel_sheet"),
                    "excel_sheets": [row.get("excel_sheet") for row in inventory_rows],
                    "status": status,
                    "confidence": float(detected.get("confidence", 0.5)) if valid_bbox else 0.0,
                    "source_page": detected.get("source_page", detected.get("page")) if valid_bbox else None,
                    "raw_text": source_text,
                    "ocr_confidence": ocr_confidence,
                    "parent_equipment": detected.get("parent_equipment") if detected else None,
                    "reason": reason,
                }
            )
            continue

        if detected is None or detected.get("missing") or not valid_bbox:
            is_sw = bool(
                excel_row.get("is_software_derived")
                or str(excel_row.get("location", "")).upper() == "DCS"
                or str(excel_row.get("io_type", "")).upper() in ("SW", "SOFTWARE")
            )
            scope_review = excel_row.get("source_visibility") == "scope_review"
            page_scope_unverified = bool(excel_row.get("pid_ref")) and not bool(
                excel_row.get("page_scope_verified")
            )
            if is_sw or scope_review or page_scope_unverified:
                status = "Pending Review"
            else:
                status = "Missing in P&ID"
            if is_sw:
                reason = "software_derived_record"
            elif scope_review:
                reason = "source_visibility_unverified"
            elif page_scope_unverified:
                reason = "source_page_mapping_unverified"
            else:
                reason = "no_valid_source_detection"

            audit.append(
                {
                    "tag_name": name,
                    "type": excel_row.get("type", "Instrument"),
                    "source_bbox": [0, 0, 0, 0],
                    "excel_row": excel_row["excel_row"],
                    "excel_rows": [int(excel_row["excel_row"])],
                    "excel_sheet": excel_row.get("excel_sheet"),
                    "excel_sheets": [excel_row.get("excel_sheet")],
                    "status": status,
                    "confidence": 0.0,
                    "source_page": None,
                    "raw_text": source_text,
                    "ocr_confidence": ocr_confidence,
                    "parent_equipment": detected.get("parent_equipment") if detected else None,
                    "reason": reason,
                }
            )
            continue

        audit.append(
            {
                "tag_name": name,
                "type": excel_row.get("type") or detected.get("type", "Instrument"),
                "source_bbox": list(bbox),
                "excel_row": excel_row["excel_row"],
                "excel_rows": [int(excel_row["excel_row"])],
                "excel_sheet": excel_row.get("excel_sheet"),
                "excel_sheets": [excel_row.get("excel_sheet")],
                "status": "Matched",
                "confidence": float(detected.get("confidence", 0.9)),
                "source_page": detected.get("source_page", detected.get("page")),
                "raw_text": source_text,
                "ocr_confidence": ocr_confidence,
                "parent_equipment": detected.get("parent_equipment"),
                "reason": None,
            }
        )

    # Include PDF-only detections not listed in Excel as Ambiguous for visibility.
    excel_names = {e["tag_name"] for e in excel_tags}
    for tag in pdf_tags:
        if tag["tag_name"] in excel_names or tag.get("missing"):
            continue
        source_bbox = tag.get("source_bbox") or [0, 0, 0, 0]
        if not has_valid_source_bbox(source_bbox):
            continue
        audit.append(
            {
                "tag_name": tag["tag_name"],
                "type": tag.get("type", "Instrument"),
                "source_bbox": list(source_bbox),
                "excel_row": 0,
                "excel_rows": [],
                "status": "Ambiguous",
                "confidence": float(tag.get("confidence", 0.5)),
                "source_page": tag.get("source_page", tag.get("page")),
                "raw_text": tag.get("raw_text"),
                "ocr_confidence": tag.get("ocr_confidence"),
                "parent_equipment": tag.get("parent_equipment"),
                "reason": "unmatched_pdf_detection",
            }
        )

    return audit


def has_valid_source_bbox(bbox: Any) -> bool:
    """Return whether a detection has a finite, non-empty source rectangle."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in bbox):
        return False
    try:
        x1, y1, x2, y2 = (float(value) for value in bbox)
    except (OverflowError, TypeError, ValueError):
        return False
    return (
        all(math.isfinite(value) for value in (x1, y1, x2, y2))
        and x1 >= 0
        and y1 >= 0
        and x2 > x1
        and y2 > y1
    )


def process_pdf(
    file_bytes: bytes,
    filename: str = "pid.pdf",
    excel_tags: Optional[List[Dict[str, Any]]] = None,
    demo_mode: bool = False,
) -> Dict[str, Any]:
    """
    Render/extract a P&ID PDF and return equipment, tags, clarifications, page count.

    Uses PyMuPDF embedded text when available. Inventory data is never treated
    as PDF evidence. Sample entities are included only when demo_mode is true.
    """
    if excel_tags is not None:
        logger.debug(
            "Excel inventory supplied for compatibility only; PDF extraction "
            "does not use it as evidence (%d rows)",
            len(excel_tags),
        )
    page_count = 1
    extracted_tags: List[Dict[str, Any]] = []
    extracted_equipment: List[Dict[str, Any]] = []
    clarifications: List[Dict[str, Any]] = []
    deferred_clarification_count = 0
    drawing_evidence: Dict[str, Any] = {
        "segments": [],
        "classified_process_lines": 0,
    }
    raster_linework: Dict[str, List[Dict[str, Any]]] = {
        "segments": [],
        "intersection_candidates": [],
    }

    if not file_bytes:
        raise PdfProcessError("PDF file is empty.")

    if fitz is None:
        if not demo_mode:
            raise PdfProcessError(
                "PDF text extraction is unavailable because PyMuPDF is not "
                "installed. Install the backend requirements to render and "
                "extract PDF evidence."
            )
        logger.warning("PyMuPDF (fitz) is not installed; using demo entities.")
    else:
        try:
            doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        except Exception as exc:
            logger.exception("Failed to open PDF '%s'", filename)
            raise PdfProcessError(f"Invalid or unreadable PDF '{filename}': {exc}") from exc

        try:
            if len(doc) == 0:
                raise PdfProcessError("PDF contains no pages.")
            (
                extracted_tags,
                extracted_equipment,
                page_count,
                has_embedded_text,
            ) = _extract_embedded_text(doc)
            drawing_evidence = _extract_drawing_evidence(doc)
            for page_index in range(len(doc)):
                page = doc[page_index]
                if not page.get_images(full=True):
                    continue
                page_linework = extract_raster_linework(page, page_index)
                raster_linework["segments"].extend(page_linework["segments"])
                raster_linework["intersection_candidates"].extend(
                    page_linework["intersection_candidates"]
                )
                logger.info(
                    "Raster evidence page %d: %d line candidates, %d unresolved intersections",
                    page_index + 1,
                    len(page_linework["segments"]),
                    len(page_linework["intersection_candidates"]),
                )
            detected_tag_pages = {
                int(item.get("source_page", item.get("page", -1)))
                for item in extracted_tags + extracted_equipment
            }
            for page_index in range(len(doc)):
                page = doc[page_index]
                if page_index in detected_tag_pages:
                    continue
                if not page.get_images(full=True) and page.get_text("text").strip():
                    continue
                ocr_tags, ocr_equipment = _extract_ocr_labels(page, page_index)
                logger.info(
                    "OCR page %d: %d tag detections, %d equipment detections",
                    page_index + 1,
                    len(ocr_tags),
                    len(ocr_equipment),
                )
                for detection, target, key in (
                    *((item, extracted_tags, "tag_name") for item in ocr_tags),
                    *((item, extracted_equipment, "tag") for item in ocr_equipment),
                ):
                    existing = next(
                        (item for item in target if item.get(key) == detection[key]),
                        None,
                    )
                    if existing is None:
                        target.append(detection)
                    else:
                        existing["ambiguous"] = True
                        existing["ambiguity_reason"] = "duplicate_source_detection"
            for crossing in find_ambiguous_process_crossings(drawing_evidence):
                page = doc[crossing["page"]]
                page_rect = page.rect
                x1, y1, x2, y2 = crossing["crop_bbox"]
                clip = fitz.Rect(
                    max(float(page_rect.x0), float(x1)),
                    max(float(page_rect.y0), float(y1)),
                    min(float(page_rect.x1), float(x2)),
                    min(float(page_rect.y1), float(y2)),
                )
                crop_data = page.get_pixmap(
                    matrix=fitz.Matrix(1.5, 1.5), clip=clip, alpha=False
                ).tobytes("png")
                clarifications.append(
                    {
                        "id": crossing["id"],
                        "location_label": (
                            f"Process line crossing on page {crossing['page'] + 1}"
                        ),
                        "question": (
                            "The source shows two process strokes crossing. "
                            "Do they connect at this point?"
                        ),
                        "crop_bbox": crossing["crop_bbox"],
                        "source_page": crossing["page"],
                        "evidence_crop_data_uri": "data:image/png;base64,"
                        + base64.b64encode(crop_data).decode("ascii"),
                        "default_recommendation": UNRESOLVED,
                        "options": [CONNECTED_JUNCTION, CROSSOVER, UNRESOLVED],
                        "status": "pending",
                    }
                )
            for nozzle in find_equipment_nozzle_endpoints(
                drawing_evidence, extracted_equipment
            ):
                if not nozzle["needs_review"]:
                    continue
                page = doc[nozzle["page"]]
                x1, y1, x2, y2 = nozzle["crop_bbox"]
                clip = fitz.Rect(x1, y1, x2, y2)
                crop_data = page.get_pixmap(
                    matrix=fitz.Matrix(1.5, 1.5), clip=clip, alpha=False
                ).tobytes("png")
                tag = nozzle["equipment_tag"]
                clarifications.append(
                    {
                        "id": nozzle["id"],
                        "location_label": f"Process pipe endpoint near {tag} on page {nozzle['page'] + 1}",
                        "question": f"Does this process pipe endpoint connect to the nozzle on {tag}?",
                        "crop_bbox": nozzle["crop_bbox"],
                        "source_page": nozzle["page"],
                        "evidence_crop_data_uri": "data:image/png;base64,"
                        + base64.b64encode(crop_data).decode("ascii"),
                        "default_recommendation": UNRESOLVED,
                        "options": [
                            f"Connected to {tag}",
                            f"Not connected to {tag}",
                            UNRESOLVED,
                        ],
                        "status": "pending",
                    }
                )
            deferred_clarification_count = max(
                0, len(clarifications) - MAX_CLARIFICATIONS_PER_RUN
            )
            clarifications = clarifications[:MAX_CLARIFICATIONS_PER_RUN]
            if (
                not demo_mode
                and not (extracted_tags or extracted_equipment)
            ):
                raise PdfProcessError(
                    f"Processed {page_count} page(s) of PDF '{filename}', but "
                    "no P&ID tag or equipment labels could be verified from "
                    "embedded text or local OCR. Check that the pages are "
                    "upright and the tag text is legible at sufficient scan "
                    "resolution. No audit was created because no source-located "
                    "tag evidence was available."
                )
            logger.info(
                "Extracted %d text tags and %d equipment labels from '%s' (%d pages)",
                len(extracted_tags),
                len(extracted_equipment),
                filename,
                page_count,
            )
        finally:
            doc.close()

    if demo_mode:
        tags, equipment = _merge_with_sample(
            extracted_tags,
            extracted_equipment,
            include_sample_tags=True,
            include_sample_equipment=True,
        )
    else:
        tags, equipment = extracted_tags, extracted_equipment
    return {
        "equipment": equipment,
        "tags": tags,
        "clarifications": clarifications,
        "deferred_clarification_count": deferred_clarification_count,
        "pdf_page_count": page_count,
        "filename": filename,
        "drawing_evidence": drawing_evidence,
        "raster_line_candidates": raster_linework["segments"],
        "raster_intersection_candidates": raster_linework[
            "intersection_candidates"
        ],
    }
