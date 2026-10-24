from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf

from graph_engine import build_process_graph
from raster_linework import extract_raster_linework


class _RasterPixmap:
    def __init__(self, pixels: np.ndarray, x: int = 0, y: int = 0) -> None:
        self.height, self.width = pixels.shape
        self.stride = self.width
        self.x = x
        self.y = y
        self.samples = pixels.tobytes()


class _RasterPage:
    def __init__(self, pixels: np.ndarray, x: int = 0, y: int = 0) -> None:
        self.pixmap = _RasterPixmap(pixels, x=x, y=y)

    def get_pixmap(self, **_kwargs: object) -> _RasterPixmap:
        return self.pixmap


def _blank_raster() -> np.ndarray:
    return np.full((180, 220), 255, dtype=np.uint8)


def _stroke(
    pixels: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
) -> None:
    x1, y1 = start
    x2, y2 = end
    if y1 == y2:
        pixels[y1 : y1 + 2, min(x1, x2) : max(x1, x2) + 1] = 0
    elif x1 == x2:
        pixels[min(y1, y2) : max(y1, y2) + 1, x1 : x1 + 2] = 0
    else:
        raise ValueError("Synthetic raster fixtures use orthogonal strokes.")


def _extract(
    pixels: np.ndarray,
    x: int = 0,
    y: int = 0,
) -> dict[str, list[dict[str, object]]]:
    return extract_raster_linework(_RasterPage(pixels, x=x, y=y), page_index=0)


def test_raster_crossings_and_branches_remain_unresolved() -> None:
    pixels = _blank_raster()
    _stroke(pixels, (20, 40), (180, 40))
    _stroke(pixels, (80, 20), (80, 100))
    _stroke(pixels, (130, 40), (130, 80))

    result = _extract(pixels)

    assert len(result["segments"]) == 3
    assert len(result["intersection_candidates"]) == 2
    assert all(
        segment["evidence_status"] == "provisional"
        and segment["kind"] == "unclassified"
        for segment in result["segments"]
    )
    assert all(
        candidate["evidence_status"] == "unresolved"
        and len(candidate["segment_ids"]) == 2
        for candidate in result["intersection_candidates"]
    )


def test_parallel_lines_and_recycle_loop_strokes_keep_distinct_geometry() -> None:
    pixels = _blank_raster()
    for y in (30, 70):
        _stroke(pixels, (20, y), (180, y))
    _stroke(pixels, (35, 110), (160, 110))
    _stroke(pixels, (35, 110), (35, 150))
    _stroke(pixels, (35, 150), (160, 150))
    _stroke(pixels, (160, 110), (160, 150))

    result = _extract(pixels)
    horizontal = [
        segment
        for segment in result["segments"]
        if segment["orientation"] == "horizontal"
    ]
    vertical = [
        segment
        for segment in result["segments"]
        if segment["orientation"] == "vertical"
    ]

    assert len(horizontal) == 4
    assert len(vertical) == 2
    assert len(result["intersection_candidates"]) == 4
    assert all(segment["page"] == 0 for segment in result["segments"])
    assert all(len(segment["source_bbox"]) == 4 for segment in result["segments"])


def test_raster_evidence_is_not_used_to_create_graph_edges() -> None:
    pixels = _blank_raster()
    _stroke(pixels, (20, 40), (180, 40))
    _stroke(pixels, (80, 20), (80, 100))
    result = _extract(pixels)

    graph = build_process_graph(
        [],
        [],
        {
            "segments": [],
            "raster_line_candidates": result["segments"],
            "raster_intersection_candidates": result["intersection_candidates"],
        },
    )

    assert graph["edges"] == []


def test_pixmap_device_origin_is_converted_to_pdf_page_points() -> None:
    pixels = _blank_raster()
    _stroke(pixels, (20, 40), (180, 40))

    result = _extract(pixels, x=40, y=20)

    horizontal = next(
        segment
        for segment in result["segments"]
        if segment["orientation"] == "horizontal"
    )
    assert horizontal["source_bbox"] == [30, 30, 111, 31]


def test_official_four_page_scan_yields_review_only_raster_evidence() -> None:
    repository = Path(__file__).resolve().parents[1]
    official_pdf = (
        repository
        / "test_cases"
        / "official_track1"
        / "Sample P&IDs_Sanitized 1.pdf"
    )
    with pymupdf.open(official_pdf) as document:
        assert len(document) == 4
        for page_index, page in enumerate(document):
            result = extract_raster_linework(page, page_index)
            assert result["segments"]
            assert all(
                segment["page"] == page_index
                and segment["kind"] == "unclassified"
                and segment["evidence_status"] == "provisional"
                and len(segment["source_bbox"]) == 4
                for segment in result["segments"]
            )
            assert all(
                candidate["evidence_status"] == "unresolved"
                for candidate in result["intersection_candidates"]
            )
