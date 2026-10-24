"""Evidence helpers for unresolved process-line crossings."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

CONNECTED_JUNCTION = "Connected Junction (4-Way Tee)"
CROSSOVER = "Crossover / No Connection"
UNRESOLVED = "Unresolved / Keep Flagged"
NOZZLE_CONNECTED = "Connected to equipment"
NOZZLE_DISCONNECTED = "Not connected to equipment"


def find_equipment_nozzle_endpoints(
    drawing_evidence: Optional[Dict[str, Any]],
    equipment: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find process endpoints aligned with one equipment nozzle.

    Exact/near-exact nozzle contacts are source geometry. A small, bounded gap
    on an axis-aligned endpoint is retained as a candidate for human review;
    proximity without an endpoint and nozzle-axis alignment is not enough.
    """
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for segment in (drawing_evidence or {}).get("segments", []):
        if segment.get("kind") != "process":
            continue
        try:
            page = int(segment["page"])
            start = tuple(float(value) for value in segment["start"])
            end = tuple(float(value) for value in segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if len(start) == 2 and len(end) == 2 and math.dist(start, end) >= 4:
            by_page.setdefault(page, []).append(
                {
                    "id": str(segment.get("id") or f"p{page}_s{len(by_page.get(page, []))}"),
                    "start": start,
                    "end": end,
                }
            )

    page_bounds = (drawing_evidence or {}).get("page_bounds", {})
    candidates_by_endpoint: Dict[Tuple[int, str, int], List[Dict[str, Any]]] = {}
    for page, segments in by_page.items():
        bounds = page_bounds.get(str(page))
        tolerance = 1.0
        if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
            tolerance = max(
                0.5,
                min(
                    2.0,
                    math.hypot(
                        float(bounds[2]) - float(bounds[0]),
                        float(bounds[3]) - float(bounds[1]),
                    )
                    * 0.001,
                ),
            )
        for segment_index, segment in enumerate(segments):
            start, end = segment["start"], segment["end"]
            horizontal = abs(start[1] - end[1]) <= tolerance
            vertical = abs(start[0] - end[0]) <= tolerance
            for endpoint_index, (point, other) in enumerate(((start, end), (end, start))):
                endpoint_matches = []
                for node in equipment:
                    if int(node.get("source_page", node.get("page", 0)) or 0) != page:
                        continue
                    bbox = node.get("source_symbol_bbox") or []
                    if len(bbox) != 4:
                        continue
                    x1, y1, x2, y2 = map(float, bbox)
                    width, height = x2 - x1, y2 - y1
                    if width <= 0 or height <= 0:
                        continue
                    minimum_dimension = min(width, height)
                    alignment_tolerance = max(2.0, minimum_dimension * 0.05)
                    max_gap = min(
                        max(width, height) * 1.1,
                        math.hypot(
                            float(bounds[2]) - float(bounds[0]),
                            float(bounds[3]) - float(bounds[1]),
                        )
                        * 0.03
                        if isinstance(bounds, (list, tuple)) and len(bounds) == 4
                        else minimum_dimension,
                    )
                    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
                    nozzle_options = []
                    point_inside = x1 <= point[0] <= x2 and y1 <= point[1] <= y2
                    other_inside = x1 <= other[0] <= x2 and y1 <= other[1] <= y2
                    if not other_inside:
                        dx, dy = point[0] - other[0], point[1] - other[1]
                        entry = -math.inf
                        exit = math.inf
                        for origin, delta, minimum, maximum in (
                            (other[0], dx, x1, x2),
                            (other[1], dy, y1, y2),
                        ):
                            if abs(delta) <= 1e-9:
                                if origin < minimum or origin > maximum:
                                    entry, exit = math.inf, -math.inf
                                    break
                                continue
                            first = (minimum - origin) / delta
                            second = (maximum - origin) / delta
                            entry = max(entry, min(first, second))
                            exit = min(exit, max(first, second))
                        enters_at_endpoint = point_inside and entry <= 1.0 <= exit
                        enters_after_endpoint = not point_inside and entry >= 1.0
                        if (
                            entry <= exit
                            and (enters_at_endpoint or enters_after_endpoint)
                        ):
                            boundary = (other[0] + entry * dx, other[1] + entry * dy)
                            nozzle_options.append(
                                (math.dist(point, boundary), boundary)
                            )
                    if horizontal and abs(point[1] - center_y) <= alignment_tolerance:
                        if x1 <= point[0] <= x2 and other[0] < point[0]:
                            nozzle_options.append(
                                (point[0] - x1, (x1, center_y))
                            )
                        if x1 <= point[0] <= x2 and other[0] > point[0]:
                            nozzle_options.append(
                                (x2 - point[0], (x2, center_y))
                            )
                        if point[0] <= x1 and other[0] <= point[0] + tolerance:
                            nozzle_options.append((x1 - point[0], (x1, center_y)))
                        if point[0] >= x2 and other[0] >= point[0] - tolerance:
                            nozzle_options.append((point[0] - x2, (x2, center_y)))
                    if vertical and abs(point[0] - center_x) <= alignment_tolerance:
                        if y1 <= point[1] <= y2 and other[1] < point[1]:
                            nozzle_options.append(
                                (point[1] - y1, (center_x, y1))
                            )
                        if y1 <= point[1] <= y2 and other[1] > point[1]:
                            nozzle_options.append(
                                (y2 - point[1], (center_x, y2))
                            )
                        if point[1] <= y1 and other[1] <= point[1] + tolerance:
                            nozzle_options.append((y1 - point[1], (center_x, y1)))
                        if point[1] >= y2 and other[1] >= point[1] - tolerance:
                            nozzle_options.append((point[1] - y2, (center_x, y2)))
                    if not nozzle_options:
                        continue
                    gap, nozzle_point = min(nozzle_options, key=lambda item: item[0])
                    if gap > max_gap:
                        continue
                    tag = str(node.get("tag") or "")
                    if not tag:
                        continue
                    candidates_by_endpoint.setdefault(
                        (page, segment["id"], endpoint_index), []
                    ).append(
                        {
                            "page": page,
                            "segment_index": segment_index,
                            "segment_id": segment["id"],
                            "endpoint_index": endpoint_index,
                            "equipment_tag": tag,
                            "point": _round_point(point),
                            "nozzle_point": _round_point(nozzle_point),
                            "gap": round(gap, 3),
                            "needs_review": gap > tolerance,
                            "id": "nozzle_"
                            + re.sub(r"[^a-zA-Z0-9_]+", "_", segment["id"])
                            + "_"
                            + re.sub(r"[^a-zA-Z0-9_]+", "_", tag.lower()),
                        }
                    )

    results = []
    for (page, segment_id, endpoint_index), candidates in candidates_by_endpoint.items():
        candidates.sort(key=lambda item: item["gap"])
        if len(candidates) > 1 and abs(candidates[0]["gap"] - candidates[1]["gap"]) <= 2.0:
            # The source endpoint has multiple competing equipment nozzles;
            # do not guess which one the pipe serves.
            continue
        candidate = candidates[0]
        if candidate["needs_review"]:
            point, nozzle = candidate["point"], candidate["nozzle_point"]
            half = 32
            bounds = page_bounds.get(str(page)) or [0, 0, 0, 0]
            candidate["crop_bbox"] = [
                max(int(bounds[0]), int(math.floor(min(point[0], nozzle[0]) - half))),
                max(int(bounds[1]), int(math.floor(min(point[1], nozzle[1]) - half))),
                min(int(bounds[2]), int(math.ceil(max(point[0], nozzle[0]) + half))),
                min(int(bounds[3]), int(math.ceil(max(point[1], nozzle[1]) + half))),
            ]
        results.append(candidate)
    return sorted(results, key=lambda item: (item["page"], item["segment_id"], item["endpoint_index"]))


def _round_point(point: Tuple[float, float]) -> Tuple[float, float]:
    return round(point[0], 2), round(point[1], 2)


def _intersection(
    first_start: Tuple[float, float],
    first_end: Tuple[float, float],
    second_start: Tuple[float, float],
    second_end: Tuple[float, float],
) -> Optional[Tuple[float, float, float, float]]:
    """Return an interior line intersection and segment fractions, if any."""
    first_dx = first_end[0] - first_start[0]
    first_dy = first_end[1] - first_start[1]
    second_dx = second_end[0] - second_start[0]
    second_dy = second_end[1] - second_start[1]
    denominator = first_dx * second_dy - first_dy * second_dx
    if abs(denominator) < 1e-8:
        return None

    delta_x = second_start[0] - first_start[0]
    delta_y = second_start[1] - first_start[1]
    first_fraction = (delta_x * second_dy - delta_y * second_dx) / denominator
    second_fraction = (delta_x * first_dy - delta_y * first_dx) / denominator
    # Endpoint meetings are tees or elbows in the drawn geometry. Only two
    # interior strokes create the competing junction/crossover interpretation.
    if not (0.03 < first_fraction < 0.97 and 0.03 < second_fraction < 0.97):
        return None

    sine = abs(denominator) / max(
        math.hypot(first_dx, first_dy) * math.hypot(second_dx, second_dy), 1e-8
    )
    if sine < 0.12:
        return None

    x = first_start[0] + first_fraction * first_dx
    y = first_start[1] + first_fraction * first_dy
    return x, y, first_fraction, second_fraction


def find_ambiguous_process_crossings(
    drawing_evidence: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find strict interior process-line crossings with a source crop rectangle.

    A geometric X alone cannot tell whether the strokes connect. The caller
    should preserve both alternatives until a reviewer selects one.
    """
    by_page: Dict[int, List[Tuple[Tuple[float, float], Tuple[float, float]]]] = {}
    for segment in (drawing_evidence or {}).get("segments", []):
        if segment.get("kind") != "process":
            continue
        try:
            page = int(segment["page"])
            start = tuple(float(value) for value in segment["start"])
            end = tuple(float(value) for value in segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if len(start) != 2 or len(end) != 2 or math.dist(start, end) < 4:
            continue
        by_page.setdefault(page, []).append((start, end))

    crossings: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
    for page, segments in by_page.items():
        for first_index, first in enumerate(segments):
            for second_index in range(first_index + 1, len(segments)):
                second = segments[second_index]
                hit = _intersection(*first, *second)
                if hit is None:
                    continue
                x, y, _, _ = hit
                point = (round(x, 2), round(y, 2))
                key = (page, round(x), round(y))
                half_size = 36
                crossings.setdefault(
                    key,
                    {
                        "id": f"crossing_p{page}_{key[1]}_{key[2]}",
                        "page": page,
                        "point": point,
                        "segment_indices": (first_index, second_index),
                        "crop_bbox": [
                            max(0, int(math.floor(x - half_size))),
                            max(0, int(math.floor(y - half_size))),
                            int(math.ceil(x + half_size)),
                            int(math.ceil(y + half_size)),
                        ],
                    },
                )

    return [crossings[key] for key in sorted(crossings)]
