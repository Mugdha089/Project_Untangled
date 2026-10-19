"""NetworkX process topology built from source-supported PDF line geometry."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from topology_evidence import (
    CONNECTED_JUNCTION,
    CROSSOVER,
    find_ambiguous_process_crossings,
    find_equipment_nozzle_endpoints,
)

logger = logging.getLogger(__name__)

# Source-detected loop instrument prefixes shown as equipment metadata when an
# explicit parent association is available.
SENSOR_PREFIXES: Set[str] = {"PT", "FT", "LT", "TT", "PI", "FI", "LI", "TI"}
CONTROLLER_PREFIXES: Set[str] = {"PC", "FC", "LC", "TC"}
VALVE_PREFIXES: Set[str] = {"LV", "FV", "XV", "PV", "HV"}
LOOP_PREFIXES: Set[str] = SENSOR_PREFIXES | CONTROLLER_PREFIXES | VALVE_PREFIXES
def _tag_prefix(tag: str) -> str:
    return tag.split("-")[0].upper() if tag else ""


def _is_loop_instrument(tag: str) -> bool:
    return _tag_prefix(tag) in LOOP_PREFIXES


def _build_equipment_nodes(
    equipment: List[Dict[str, Any]],
    audit_tags: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build detected equipment nodes and attach supported matched loop tags."""
    nodes: List[Dict[str, Any]] = []
    seen_tags: Set[str] = set()
    for eq in equipment:
        tag = eq.get("tag")
        if not tag or tag in seen_tags:
            if tag:
                logger.warning("Duplicate equipment tag %s was omitted from graph nodes", tag)
            continue
        seen_tags.add(tag)
        nodes.append(
            {
                "id": eq.get("id") or f"eq_{tag.lower().replace('-', '')}",
                "tag": tag,
                "type": eq["type"],
                "label": eq.get("label") or f"{eq['type'].title()} {tag}",
                "source_bbox": list(eq.get("source_bbox") or [0, 0, 0, 0]),
                "source_symbol_bbox": list(eq.get("source_symbol_bbox") or []),
                "source_page": int(eq.get("source_page", eq.get("page", 0))),
                "collapsed_tags": [],
                "duty_standby": bool(eq.get("duty_standby_group")),
            }
        )

    # Only use the parent association supplied by the evidence pipeline. Do not
    # guess a parent from tag numbering when the source does not establish one.
    node_by_tag = {n["tag"]: n for n in nodes}

    for audit in audit_tags:
        tag_name = audit.get("tag_name", "")
        if not _is_loop_instrument(tag_name):
            continue
        if audit.get("status") != "Matched":
            continue

        parent = audit.get("parent_equipment")
        if parent and parent in node_by_tag:
            if tag_name not in node_by_tag[parent]["collapsed_tags"]:
                node_by_tag[parent]["collapsed_tags"].append(tag_name)

    return _order_nodes_left_to_right(nodes)


def _order_nodes_left_to_right(
    nodes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Order positioned equipment by horizontal location; retain input order otherwise."""
    if not nodes or any(
        not node.get("source_bbox")
        or len(node["source_bbox"]) < 4
        or node["source_bbox"] == [0, 0, 0, 0]
        for node in nodes
    ):
        return nodes

    return sorted(
        nodes,
        key=lambda node: (
            (node["source_bbox"][0] + node["source_bbox"][2]) / 2.0,
            node["tag"],
        ),
    )


def _point_on_segment(
    point: Tuple[float, float],
    start: Tuple[float, float],
    end: Tuple[float, float],
    tolerance: float = 1.0,
) -> bool:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.dist(point, start) <= tolerance
    projection = (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / length_squared
    fraction_tolerance = tolerance / math.sqrt(length_squared)
    if projection < -fraction_tolerance or projection > 1 + fraction_tolerance:
        return False
    closest = (start[0] + projection * dx, start[1] + projection * dy)
    return math.dist(point, closest) <= tolerance


def _project_point(
    point: Tuple[float, float],
    start: Tuple[float, float],
    end: Tuple[float, float],
) -> Tuple[float, Tuple[float, float]]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.dist(point, start), start
    fraction = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / length_squared,
        ),
    )
    projected = (start[0] + fraction * dx, start[1] + fraction * dy)
    return math.dist(point, projected), projected


def _coordinate_key(point: Tuple[float, float]) -> Tuple[float, float]:
    return round(point[0], 2), round(point[1], 2)


def _endpoint_tolerance(page_bounds: Optional[List[float]]) -> float:
    """Return a scale-aware snap tolerance in PDF points (0.05–0.14% of diagonal).

    The tolerance is bounded to 0.5–2.0 points so page size affects scaling
    without allowing visibly separated line ends to become connected.
    """
    if page_bounds is None or len(page_bounds) != 4:
        return 1.0
    width = max(0.0, float(page_bounds[2]) - float(page_bounds[0]))
    height = max(0.0, float(page_bounds[3]) - float(page_bounds[1]))
    if width == 0.0 or height == 0.0:
        return 1.0
    return max(0.5, min(2.0, math.hypot(width, height) * 0.001))


def _snap_segment_endpoints(
    segments: List[Dict[str, Any]], tolerance: float
) -> None:
    """Join only line endpoints within the page-scale geometric tolerance."""
    endpoints = [
        (segment_index, endpoint_name, segment[endpoint_name])
        for segment_index, segment in enumerate(segments)
        for endpoint_name in ("start", "end")
    ]
    cell_size = max(tolerance, 0.1)
    buckets: Dict[Tuple[int, int], List[int]] = {}
    clusters: Dict[int, List[int]] = {}
    endpoint_cluster: Dict[int, int] = {}
    for index, (_, _, point) in enumerate(endpoints):
        cell = (math.floor(point[0] / cell_size), math.floor(point[1] / cell_size))
        nearby: Set[int] = set()
        for x_offset in (-1, 0, 1):
            for y_offset in (-1, 0, 1):
                nearby.update(
                    buckets.get((cell[0] + x_offset, cell[1] + y_offset), [])
                )
        candidate_clusters = sorted(
            {endpoint_cluster[candidate] for candidate in nearby}
        )
        selected_cluster = next(
            (
                cluster_id
                for cluster_id in candidate_clusters
                if all(
                    math.dist(point, endpoints[member][2]) <= tolerance
                    for member in clusters[cluster_id]
                )
            ),
            None,
        )
        if selected_cluster is None:
            selected_cluster = index
            clusters[selected_cluster] = []
        clusters[selected_cluster].append(index)
        endpoint_cluster[index] = selected_cluster
        buckets.setdefault(cell, []).append(index)

    representatives = {
        root: _coordinate_key(
            (
                sum(endpoints[index][2][0] for index in members) / len(members),
                sum(endpoints[index][2][1] for index in members) / len(members),
            )
        )
        for root, members in clusters.items()
    }
    for index, (segment_index, endpoint_name, _) in enumerate(endpoints):
        segments[segment_index][endpoint_name] = representatives[
            endpoint_cluster[index]
        ]


def _source_bbox_for_path(points: List[Tuple[float, float]]) -> List[int]:
    return [
        int(round(min(point[0] for point in points))),
        int(round(min(point[1] for point in points))),
        int(round(max(point[0] for point in points))),
        int(round(max(point[1] for point in points))),
    ]


def _build_geometry_edges(
    nodes: List[Dict[str, Any]],
    drawing_evidence: Optional[Dict[str, Any]],
    crossing_resolutions: Optional[Dict[str, str]] = None,
    nozzle_resolutions: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """Trace legend-classified process strokes and retain branch junctions."""
    segments_by_page: Dict[int, List[Dict[str, Any]]] = {}
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
        segments_by_page.setdefault(page, []).append(
            {
                "id": str(segment.get("id") or f"p{page}_s{len(segments_by_page.get(page, []))}"),
                "start": start,
                "end": end,
            }
        )

    edges: List[Dict[str, Any]] = []
    junction_nodes: List[Dict[str, Any]] = []
    unresolved_equipment = 0
    junction_index = 0

    for page, segments in segments_by_page.items():
        page_bounds = (drawing_evidence or {}).get("page_bounds", {}).get(
            str(page)
        )
        tolerance = _endpoint_tolerance(page_bounds)
        _snap_segment_endpoints(segments, tolerance)
        graph = nx.Graph()
        endpoints = {
            _coordinate_key(point)
            for segment in segments
            for point in (segment["start"], segment["end"])
        }
        split_points: Dict[int, Set[Tuple[float, float]]] = {
            index: {
                _coordinate_key(segment["start"]),
                _coordinate_key(segment["end"]),
            }
            for index, segment in enumerate(segments)
        }

        for index, segment in enumerate(segments):
            for point in endpoints:
                if _point_on_segment(
                    point, segment["start"], segment["end"], tolerance
                ):
                    split_points[index].add(point)

        for crossing in find_ambiguous_process_crossings(drawing_evidence):
            if crossing["page"] != page:
                continue
            if (crossing_resolutions or {}).get(crossing["id"]) != CONNECTED_JUNCTION:
                continue
            first_index, second_index = crossing["segment_indices"]
            if first_index >= len(segments) or second_index >= len(segments):
                continue
            point = _coordinate_key(tuple(crossing["point"]))
            split_points[first_index].add(point)
            split_points[second_index].add(point)

        equipment_points: Dict[str, Set[Tuple[float, float]]] = {}
        provisional_nozzle_segments: Set[str] = set()
        confirmed_nozzle_segments: Set[str] = set()
        nodes_by_tag = {str(node["tag"]): node for node in nodes}
        matched_equipment: Set[str] = set()

        # A process stroke that traverses the full symbol bounds on its
        # centreline is direct geometric evidence of an in-line connection.
        # Add only the two symbol-boundary points; nearby parallel strokes do
        # not satisfy this intersection test.
        for equipment_node in nodes:
            if int(equipment_node.get("source_page", 0)) != page:
                continue
            symbol_bbox = equipment_node.get("source_symbol_bbox") or []
            if len(symbol_bbox) != 4:
                continue
            x1, y1, x2, y2 = map(float, symbol_bbox)
            center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
            alignment_tolerance = max(2.0, min(x2 - x1, y2 - y1) * 0.05)
            for index, segment in enumerate(segments):
                start, end = segment["start"], segment["end"]
                if (
                    abs(start[1] - end[1]) <= tolerance
                    and abs((start[1] + end[1]) / 2 - center_y)
                    <= alignment_tolerance
                    and min(start[0], end[0]) <= x1 + tolerance
                    and max(start[0], end[0]) >= x2 - tolerance
                ):
                    points = {
                        _coordinate_key((x1, (start[1] + end[1]) / 2)),
                        _coordinate_key((x2, (start[1] + end[1]) / 2)),
                    }
                elif (
                    abs(start[0] - end[0]) <= tolerance
                    and abs((start[0] + end[0]) / 2 - center_x)
                    <= alignment_tolerance
                    and min(start[1], end[1]) <= y1 + tolerance
                    and max(start[1], end[1]) >= y2 - tolerance
                ):
                    points = {
                        _coordinate_key(((start[0] + end[0]) / 2, y1)),
                        _coordinate_key(((start[0] + end[0]) / 2, y2)),
                    }
                else:
                    continue
                split_points[index].update(points)
                equipment_points.setdefault(str(equipment_node["tag"]), set()).update(points)
                matched_equipment.add(str(equipment_node["tag"]))

        nozzle_candidates = find_equipment_nozzle_endpoints(drawing_evidence, nodes)
        for nozzle in nozzle_candidates:
            if nozzle["page"] != page:
                continue
            selected = (nozzle_resolutions or {}).get(nozzle["id"])
            tag = nozzle["equipment_tag"]
            connected_option = f"Connected to {tag}"
            disconnected_option = f"Not connected to {tag}"
            if nozzle["needs_review"] and selected == disconnected_option:
                continue
            if nozzle["needs_review"] and selected not in (
                None,
                connected_option,
                "Unresolved / Keep Flagged",
            ):
                continue
            node = nodes_by_tag.get(tag)
            if node is None or int(node.get("source_page", 0)) != page:
                continue
            point = _coordinate_key(tuple(nozzle["point"]))
            segment_index = int(nozzle["segment_index"])
            if segment_index >= len(segments):
                continue
            split_points[segment_index].add(point)
            equipment_points.setdefault(tag, set()).add(point)
            matched_equipment.add(tag)
            if nozzle["needs_review"] and selected == connected_option:
                confirmed_nozzle_segments.add(nozzle["segment_id"])
            elif nozzle["needs_review"]:
                provisional_nozzle_segments.add(nozzle["segment_id"])

        for equipment_node in nodes:
            if int(equipment_node.get("source_page", 0)) != page:
                continue
            bbox = equipment_node.get("source_bbox") or [0, 0, 0, 0]
            symbol_bbox = equipment_node.get("source_symbol_bbox") or []
            if (
                len(bbox) != 4
                or bbox == [0, 0, 0, 0]
                or len(symbol_bbox) != 4
                or not equipment_points.get(str(equipment_node["tag"]))
            ):
                unresolved_equipment += 1

        point_owners: Dict[Tuple[float, float], List[str]] = {}
        for tag, points in equipment_points.items():
            for point in points:
                point_owners.setdefault(point, []).append(tag)

        def graph_vertex(point: Tuple[float, float]) -> Any:
            owners = point_owners.get(point, [])
            if len(owners) == 1:
                return ("equipment", owners[0])
            return ("coordinate", point)

        for index, segment in enumerate(segments):
            points = sorted(
                split_points[index],
                key=lambda point: (
                    point[0] - segment["start"][0]
                )
                * (segment["end"][0] - segment["start"][0])
                + (point[1] - segment["start"][1])
                * (segment["end"][1] - segment["start"][1]),
            )
            for first, second in zip(points, points[1:]):
                source, target = graph_vertex(first), graph_vertex(second)
                if source == target:
                    continue
                existing = graph.get_edge_data(source, target)
                if existing is None:
                    graph.add_edge(
                        source,
                        target,
                        page=page,
                        points=[first, second],
                        source_segment_ids=[segment["id"]],
                    )
                else:
                    existing.setdefault("source_segment_ids", []).append(
                        segment["id"]
                    )

        for tag, points in equipment_points.items():
            if any(len(point_owners.get(point, [])) > 1 for point in points):
                unresolved_equipment += 1
            graph.add_node(("equipment", tag))

        # A coordinate where three or more source pipe strokes meet is kept as
        # an explicit junction; non-junction geometry is compressed below.
        meaningful: Set[Any] = {
            vertex
            for vertex in graph.nodes
            if vertex[0] == "equipment"
            or graph.degree(vertex) != 2
        }
        graph_node_by_tag = {node["tag"]: node for node in nodes}
        output_tag: Dict[Any, str] = {}
        for vertex in sorted(meaningful, key=lambda item: (item[0], item[1])):
            if vertex[0] == "equipment":
                output_tag[vertex] = vertex[1]
            elif graph.degree(vertex) >= 3:
                point = vertex[1]
                junction_index += 1
                tag = f"JUNCTION-{junction_index}"
                identifier = f"junction_p{page}_{int(round(point[0]))}_{int(round(point[1]))}"
                junction_nodes.append(
                    {
                        "id": identifier,
                        "tag": tag,
                        "type": "junction",
                        "label": "Process pipe junction",
                        "source_bbox": [
                            int(round(point[0])),
                            int(round(point[1])),
                            int(round(point[0])),
                            int(round(point[1])),
                        ],
                        "source_page": page,
                        "collapsed_tags": [],
                        "duty_standby": False,
                    }
                )
                output_tag[vertex] = tag

        visited: Set[frozenset] = set()
        for start_vertex in meaningful:
            start_tag = output_tag.get(start_vertex)
            if start_tag is None:
                continue
            for neighbor in graph.neighbors(start_vertex):
                path_key = frozenset((start_vertex, neighbor))
                if path_key in visited:
                    continue
                visited.add(path_key)
                path_points: List[Tuple[float, float]] = []
                path_segment_ids: List[str] = []
                previous, current = start_vertex, neighbor
                while current not in meaningful:
                    edge_data = graph.get_edge_data(previous, current) or {}
                    path_points.extend(edge_data.get("points", []))
                    path_segment_ids.extend(
                        edge_data.get("source_segment_ids", [])
                    )
                    next_vertices = [
                        candidate
                        for candidate in graph.neighbors(current)
                        if candidate != previous
                    ]
                    if len(next_vertices) != 1:
                        break
                    next_vertex = next_vertices[0]
                    visited.add(frozenset((current, next_vertex)))
                    previous, current = current, next_vertex
                edge_data = graph.get_edge_data(previous, current) or {}
                path_points.extend(edge_data.get("points", []))
                path_segment_ids.extend(edge_data.get("source_segment_ids", []))
                target_tag = output_tag.get(current)
                if target_tag is None or start_tag == target_tag:
                    continue
                if start_tag not in graph_node_by_tag and not any(
                    node["tag"] == start_tag for node in junction_nodes
                ):
                    continue
                if target_tag not in graph_node_by_tag and not any(
                    node["tag"] == target_tag for node in junction_nodes
                ):
                    continue
                pair = tuple(sorted((start_tag, target_tag)))
                unique_points = list(dict.fromkeys(path_points))
                path_segment_ids = list(dict.fromkeys(path_segment_ids))
                user_confirmed_crossing = any(
                    (crossing_resolutions or {}).get(crossing["id"])
                    == CONNECTED_JUNCTION
                    and crossing["page"] == page
                    and any(
                        math.dist(point, tuple(crossing["point"])) <= tolerance
                        for point in unique_points
                    )
                    for crossing in find_ambiguous_process_crossings(
                        drawing_evidence
                    )
                )
                path_uses_confirmed_nozzle = bool(
                    set(path_segment_ids) & confirmed_nozzle_segments
                )
                path_uses_provisional_nozzle = bool(
                    set(path_segment_ids) & provisional_nozzle_segments
                )
                existing_edge = next(
                    (
                        edge
                        for edge in edges
                        if (edge["source"], edge["target"]) == pair
                        or (edge["target"], edge["source"]) == pair
                    ),
                    None,
                )
                if existing_edge is None:
                    edges.append(
                        {
                            "id": f"edge_{pair[0]}_{pair[1]}".replace("-", "").lower(),
                            "source": pair[0],
                            "target": pair[1],
                            "flow_direction": "undirected",
                            "relation": "process_pipe",
                            "evidence_status": (
                                "user_confirmed_crossing"
                                if user_confirmed_crossing
                                else "user_confirmed_nozzle"
                                if path_uses_confirmed_nozzle
                                else "provisional_nozzle_alignment"
                                if path_uses_provisional_nozzle
                                else "source_geometry"
                            ),
                            "source_segment_ids": path_segment_ids,
                            "source_page": page,
                            "source_bbox": _source_bbox_for_path(unique_points)
                            if unique_points
                            else [0, 0, 0, 0],
                        }
                    )
                else:
                    if user_confirmed_crossing:
                        existing_edge["evidence_status"] = "user_confirmed_crossing"
                    elif path_uses_confirmed_nozzle:
                        existing_edge["evidence_status"] = "user_confirmed_nozzle"
                    elif (
                        path_uses_provisional_nozzle
                        and existing_edge.get("evidence_status") == "source_geometry"
                    ):
                        existing_edge["evidence_status"] = "provisional_nozzle_alignment"
                    existing_edge["source_segment_ids"] = list(
                        dict.fromkeys(
                            existing_edge.get("source_segment_ids", [])
                            + path_segment_ids
                        )
                    )
                    if unique_points:
                        existing_bbox = existing_edge.get("source_bbox") or [0, 0, 0, 0]
                        path_bbox = _source_bbox_for_path(unique_points)
                        existing_edge["source_bbox"] = [
                            min(existing_bbox[0], path_bbox[0]),
                            min(existing_bbox[1], path_bbox[1]),
                            max(existing_bbox[2], path_bbox[2]),
                            max(existing_bbox[3], path_bbox[3]),
                        ]

    return edges, junction_nodes, unresolved_equipment


def build_process_graph(
    equipment: List[Dict[str, Any]],
    audit_tags: List[Dict[str, Any]],
    drawing_evidence: Optional[Dict[str, Any]] = None,
    crossing_resolutions: Optional[Dict[str, str]] = None,
    nozzle_resolutions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Construct process topology only from legend-classified source pipe geometry.
    """
    nodes = _build_equipment_nodes(equipment, audit_tags)
    graph = nx.Graph()
    for node in nodes:
        graph.add_node(node["tag"], **node)

    edges, junction_nodes, unresolved_equipment = _build_geometry_edges(
        nodes, drawing_evidence, crossing_resolutions, nozzle_resolutions
    )
    nodes.extend(junction_nodes)
    for node in junction_nodes:
        graph.add_node(node["tag"], **node)
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"], **edge)

    if not nodes:
        integrity = "Unverified — no equipment was detected in the PDF."
    elif not (drawing_evidence or {}).get("classified_process_lines"):
        integrity = (
            "Unverified — no legend-classified process-pipe geometry was found."
        )
    elif not edges:
        integrity = (
            "Unverified — process-pipe geometry was found, but no equipment "
            "connections could be established."
        )
    else:
        integrity = (
            f"Partially verified — {len(edges)} source-supported process "
            "connections; flow direction is unresolved."
        )
        if unresolved_equipment:
            integrity += f" {unresolved_equipment} equipment location(s) unresolved."

    crossings = find_ambiguous_process_crossings(drawing_evidence)
    resolutions = crossing_resolutions or {}
    confirmed_crossings = sum(
        resolutions.get(crossing["id"]) in {CONNECTED_JUNCTION, CROSSOVER}
        for crossing in crossings
    )
    unresolved_crossings = len(crossings) - confirmed_crossings
    if confirmed_crossings:
        integrity += f" {confirmed_crossings} crossing interpretation(s) are user-confirmed."
    if unresolved_crossings:
        integrity += (
            f" {unresolved_crossings} process-line crossing(s) remain unresolved; "
            "their connectivity is provisional."
        )
    provisional_nozzles = {
        edge["id"]
        for edge in edges
        if edge.get("evidence_status") == "provisional_nozzle_alignment"
    }
    confirmed_nozzles = {
        edge["id"]
        for edge in edges
        if edge.get("evidence_status") == "user_confirmed_nozzle"
    }
    if provisional_nozzles:
        integrity += (
            f" {len(provisional_nozzles)} equipment connection(s) use aligned "
            "nozzle geometry pending review; connectivity is provisional."
        )
    if confirmed_nozzles:
        integrity += f" {len(confirmed_nozzles)} equipment connection(s) are user-confirmed."

    logger.info(
        "Graph built from source geometry: %d equipment/junction nodes, %d edges, status=%s",
        len(nodes),
        len(edges),
        integrity,
    )

    # Strip internal helper fields before serialisation.
    serialisable_nodes = []
    for node in nodes:
        clean = {
            "id": node["id"],
            "tag": node["tag"],
            "type": node["type"],
            "label": node["label"],
            "source_bbox": [int(v) for v in node["source_bbox"]],
            "source_page": int(node.get("source_page", 0)),
            "source_symbol_bbox": (
                [int(v) for v in node["source_symbol_bbox"]]
                if node.get("source_symbol_bbox")
                else None
            ),
            "collapsed_tags": list(node.get("collapsed_tags") or []),
            "duty_standby": bool(node.get("duty_standby", False)),
        }
        serialisable_nodes.append(clean)

    return {
        "nodes": serialisable_nodes,
        "edges": edges,
        "graph_integrity": integrity,
        "edge_count_before_layout": len(edges),
        "edge_count_after_layout": len(edges),
        "changed_edges": 0,
        "retained_equipment": sum(1 for node in nodes if node["type"] != "junction"),
        "user_confirmed_crossings": sum(
            choice in {CONNECTED_JUNCTION, CROSSOVER}
            for choice in (crossing_resolutions or {}).values()
        ),
        "nx_graph": graph,
    }


def generate_auto_layout(
    nodes: List[Dict[str, Any]],
    x_spacing: float = 220.0,
    y_center: float = 200.0,
) -> Dict[str, Tuple[float, float]]:
    """
    Produce a simple left-to-right layout schema.

    Layout only assigns coordinates; it must not alter graph topology.
    """
    positions: Dict[str, Tuple[float, float]] = {}
    for index, node in enumerate(nodes):
        positions[node["tag"]] = (80.0 + index * x_spacing, y_center)
    return positions


def apply_ambiguity_resolution(
    edges: List[Dict[str, Any]],
    item_id: str,
    selected_option: str,
    retained_equipment: int,
    total_tags: int,
    matched_tags: int,
    processing_time_seconds: float = 0.12,
) -> Dict[str, Any]:
    """Record review context without claiming the source graph was recalculated."""
    updated_edges = [dict(e) for e in edges]
    if updated_edges:
        integrity = (
            "Partially verified — source-supported topology retained; "
            "flow direction and unreviewed connections remain unresolved."
        )
    else:
        integrity = (
            "Unverified — no source-supported process connections are available; "
            "the clarification did not validate graph topology."
        )

    kpis = {
        "total_tags": total_tags,
        "matched_tags": matched_tags,
        "retained_equipment": retained_equipment,
        "graph_integrity": integrity,
        "processing_time_seconds": round(processing_time_seconds, 3),
    }

    logger.info(
        "Ambiguity %s recorded as '%s'; topology unchanged → integrity=%s",
        item_id,
        selected_option,
        integrity,
    )

    return {"kpis": kpis, "edges": updated_edges}
