"""Conservative raster linework candidates that never become graph edges."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import numpy as np

RASTER_RENDER_SCALE = 2.0
RASTER_THRESHOLD = 160
MINIMUM_LINE_LENGTH_POINTS = 10.0
MAXIMUM_STROKE_WIDTH_POINTS = 3.0


def _pixel_runs(values: np.ndarray) -> List[Tuple[int, int]]:
    occupied = np.flatnonzero(values)
    if occupied.size == 0:
        return []

    split_points = np.flatnonzero(np.diff(occupied) > 2) + 1
    groups = np.split(occupied, split_points)
    return [(int(group[0]), int(group[-1]) + 1) for group in groups]


def _axis_tracks(mask: np.ndarray, scale: float) -> List[Dict[str, int]]:
    tracks: List[Dict[str, int]] = []
    active_tracks: List[int] = []
    maximum_stroke_pixels = max(2, int(math.ceil(MAXIMUM_STROKE_WIDTH_POINTS * scale)))
    minimum_length_pixels = int(math.ceil(MINIMUM_LINE_LENGTH_POINTS * scale))

    for minor_position, scanline in enumerate(mask):
        used_tracks: set[int] = set()
        active_tracks = [
            track_index
            for track_index in active_tracks
            if minor_position - tracks[track_index]["last_minor"] <= 2
        ]
        for run_start, run_end in _pixel_runs(scanline):
            run_width = run_end - run_start
            if run_width < minimum_length_pixels - 2:
                continue
            matches = []
            for track_index in active_tracks:
                track = tracks[track_index]
                overlap = max(
                    0,
                    min(run_end, track["max_major"])
                    - max(run_start, track["min_major"]),
                )
                coverage = overlap / max(
                    run_width, track["max_major"] - track["min_major"]
                )
                if coverage >= 0.5 and track_index not in used_tracks:
                    matches.append((coverage, track_index))

            if matches:
                _, selected_index = max(matches)
                track = tracks[selected_index]
                track["min_major"] = min(track["min_major"], run_start)
                track["max_major"] = max(track["max_major"], run_end)
                track["last_minor"] = minor_position
                used_tracks.add(selected_index)
            else:
                tracks.append(
                    {
                        "min_major": run_start,
                        "max_major": run_end,
                        "first_minor": minor_position,
                        "last_minor": minor_position,
                    }
                )
                track_index = len(tracks) - 1
                active_tracks.append(track_index)
                used_tracks.add(track_index)

    return [
        track
        for track in tracks
        if track["max_major"] - track["min_major"] >= minimum_length_pixels
        and track["last_minor"] - track["first_minor"] + 1
        <= maximum_stroke_pixels
    ]


def _source_bbox(x1: float, y1: float, x2: float, y2: float) -> List[int]:
    return [
        math.floor(x1),
        math.floor(y1),
        math.ceil(x2),
        math.ceil(y2),
    ]


def extract_raster_linework(page: Any, page_index: int) -> Dict[str, List[Dict[str, Any]]]:
    """Find orthogonal dark-pixel runs and unresolved intersections in PDF points.

    The detector deliberately does not infer line purpose, connectivity, or flow
    direction. Its output is evidence for review, not input to graph construction.
    """
    import pymupdf

    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(RASTER_RENDER_SCALE, RASTER_RENDER_SCALE),
        colorspace=pymupdf.csGRAY,
        alpha=False,
    )
    pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.stride
    )[:, : pixmap.width]
    dark_pixels = pixels < RASTER_THRESHOLD
    raster_segments: List[Dict[str, Any]] = []
    scale = RASTER_RENDER_SCALE

    for orientation, scanlines in (
        ("horizontal", dark_pixels),
        ("vertical", dark_pixels.T),
    ):
        for track in _axis_tracks(scanlines, scale):
            if orientation == "horizontal":
                x1 = (pixmap.x + track["min_major"]) / scale
                x2 = (pixmap.x + track["max_major"]) / scale
                y1 = (pixmap.y + track["first_minor"]) / scale
                y2 = (pixmap.y + track["last_minor"] + 1) / scale
                start = [x1, (y1 + y2) / 2]
                end = [x2, (y1 + y2) / 2]
            else:
                x1 = (pixmap.x + track["first_minor"]) / scale
                x2 = (pixmap.x + track["last_minor"] + 1) / scale
                y1 = (pixmap.y + track["min_major"]) / scale
                y2 = (pixmap.y + track["max_major"]) / scale
                start = [(x1 + x2) / 2, y1]
                end = [(x1 + x2) / 2, y2]

            segment_id = (
                f"raster_p{page_index}_{orientation}_{len(raster_segments)}"
            )
            raster_segments.append(
                {
                    "id": segment_id,
                    "page": page_index,
                    "start": [round(value, 2) for value in start],
                    "end": [round(value, 2) for value in end],
                    "source_bbox": _source_bbox(x1, y1, x2, y2),
                    "orientation": orientation,
                    "kind": "unclassified",
                    "evidence_status": "provisional",
                }
            )

    horizontal = [
        segment for segment in raster_segments
        if segment["orientation"] == "horizontal"
    ]
    vertical = [
        segment for segment in raster_segments
        if segment["orientation"] == "vertical"
    ]
    intersections: Dict[Tuple[float, float], Dict[str, Any]] = {}
    for horizontal_segment in horizontal:
        hx1, hy = horizontal_segment["start"]
        hx2 = horizontal_segment["end"][0]
        for vertical_segment in vertical:
            vx, vy1 = vertical_segment["start"]
            vy2 = vertical_segment["end"][1]
            if min(hx1, hx2) <= vx <= max(hx1, hx2) and min(vy1, vy2) <= hy <= max(vy1, vy2):
                point = (round(vx, 1), round(hy, 1))
                candidate = intersections.setdefault(
                    point,
                    {
                        "id": f"raster_p{page_index}_intersection_{len(intersections)}",
                        "page": page_index,
                        "point": [point[0], point[1]],
                        "source_bbox": _source_bbox(
                            vx - 2, hy - 2, vx + 2, hy + 2
                        ),
                        "segment_ids": [],
                        "evidence_status": "unresolved",
                    },
                )
                candidate["segment_ids"] = sorted(
                    set(candidate["segment_ids"])
                    | {horizontal_segment["id"], vertical_segment["id"]}
                )

    return {
        "segments": raster_segments,
        "intersection_candidates": list(intersections.values()),
    }
