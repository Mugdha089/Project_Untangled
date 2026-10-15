"""NetworkX process topology built from source-supported PDF line geometry."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

# Secondary loop instrument prefixes collapsed into equipment metadata pills.
SENSOR_PREFIXES: Set[str] = {"PT", "FT", "LT", "TT", "PI", "FI", "LI", "TI"}
CONTROLLER_PREFIXES: Set[str] = {"PC", "FC", "LC", "TC"}
VALVE_PREFIXES: Set[str] = {"LV", "FV", "XV", "PV", "HV"}
LOOP_PREFIXES: Set[str] = SENSOR_PREFIXES | CONTROLLER_PREFIXES | VALVE_PREFIXES
CONTROL_LOOP_ASSIGNMENTS: Dict[str, str] = {
    "FT-10": "P-201",
    "FV-3-3040": "P-201",
    "FT-11": "P-504",
    "FV-3-3041": "P-504",
}

def _tag_prefix(tag: str) -> str:
    return tag.split("-")[0].upper() if tag else ""


def _is_loop_instrument(tag: str) -> bool:
    return _tag_prefix(tag) in LOOP_PREFIXES


def _build_equipment_nodes(
    equipment: List[Dict[str, Any]],
    audit_tags: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build one node per detected item and attach control-loop tags."""
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

    # Map excel/pdf tags onto nearest primary equipment for loop collapse.
    node_by_tag = {n["tag"]: n for n in nodes}

    for audit in audit_tags:
        tag_name = audit.get("tag_name", "")
        if not _is_loop_instrument(tag_name):
            continue
        if audit.get("status") == "Missing in P&ID":
            # Still attach missing tags as collapsed metadata on parent equipment
            # so the I/O list remains visible on the sketch.
            parent = audit.get("parent_equipment")
            if parent and parent in node_by_tag:
                if tag_name not in node_by_tag[parent]["collapsed_tags"]:
                    node_by_tag[parent]["collapsed_tags"].append(tag_name)
            continue

        parent = audit.get("parent_equipment")
        parent = CONTROL_LOOP_ASSIGNMENTS.get(tag_name, parent)
        if parent not in node_by_tag:
            # Fallback: attach sensors to nearest equipment by prefix heuristics.
            parent = _heuristic_parent(tag_name, list(node_by_tag.keys()))
        if parent and parent in node_by_tag:
            if tag_name not in node_by_tag[parent]["collapsed_tags"]:
                node_by_tag[parent]["collapsed_tags"].append(tag_name)

    return _order_nodes_left_to_right(nodes)


def _heuristic_parent(tag_name: str, equipment_tags: List[str]) -> Optional[str]:
    """Prefer equipment whose numeric id is closest to the instrument number."""
    try:
        tag_num = int("".join(ch for ch in tag_name.split("-")[-1] if ch.isdigit()) or "0")
    except ValueError:
        return equipment_tags[0] if equipment_tags else None

    best = None
    best_delta = float("inf")
    for eq_tag in equipment_tags:
        try:
            eq_num = int("".join(ch for ch in eq_tag.split("-")[-1] if ch.isdigit()) or "0")
        except ValueError:
            continue
        delta = abs(eq_num - tag_num)
        if delta < best_delta:
            best_delta = delta
            best = eq_tag
    return best


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
    if projection < -tolerance or projection > 1 + tolerance:
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
            {"start": start, "end": end}
        )

    edges: List[Dict[str, Any]] = []
    junction_nodes: List[Dict[str, Any]] = []
    unresolved_equipment = 0
    junction_index = 0

    for page, segments in segments_by_page.items():
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
                if _point_on_segment(point, segment["start"], segment["end"]):
                    split_points[index].add(point)

        equipment_points: Dict[str, Set[Tuple[float, float]]] = {}
        for equipment_node in nodes:
            if int(equipment_node.get("source_page", 0)) != page:
                continue
            bbox = equipment_node.get("source_bbox") or [0, 0, 0, 0]
            if len(bbox) != 4 or bbox == [0, 0, 0, 0]:
                unresolved_equipment += 1
                continue
            symbol_bbox = equipment_node.get("source_symbol_bbox") or []
            if len(symbol_bbox) != 4:
                unresolved_equipment += 1
                continue
            anchor_bbox = symbol_bbox
            center = (
                (float(anchor_bbox[0]) + float(anchor_bbox[2])) / 2,
                (float(anchor_bbox[1]) + float(anchor_bbox[3])) / 2,
            )
            projections = []
            for index, segment in enumerate(segments):
                distance, projected = _project_point(
                    center, segment["start"], segment["end"]
                )
                margin = 18.0
                in_symbol_region = (
                    float(symbol_bbox[0]) - margin
                    <= projected[0]
                    <= float(symbol_bbox[2]) + margin
                    and float(symbol_bbox[1]) - margin
                    <= projected[1]
                    <= float(symbol_bbox[3]) + margin
                )
                projections.append(
                    (distance, index, _coordinate_key(projected), in_symbol_region)
                )
            if not projections:
                unresolved_equipment += 1
                continue
            symbol_candidates = {
                (index, point)
                for _, index, point, in_symbol_region in projections
                if in_symbol_region
            }
            if not symbol_candidates:
                unresolved_equipment += 1
                continue
            candidates = symbol_candidates
            points = set()
            for index, point in candidates:
                split_points[index].add(point)
                points.add(point)
            if points:
                equipment_points[equipment_node["tag"]] = points
            else:
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
                graph.add_edge(source, target, page=page, points=[first, second])

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
                previous, current = start_vertex, neighbor
                while current not in meaningful:
                    edge_data = graph.get_edge_data(previous, current) or {}
                    path_points.extend(edge_data.get("points", []))
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
                if any(
                    (edge["source"], edge["target"]) == pair
                    or (edge["target"], edge["source"]) == pair
                    for edge in edges
                ):
                    continue
                unique_points = list(dict.fromkeys(path_points))
                edges.append(
                    {
                        "id": f"edge_{pair[0]}_{pair[1]}".replace("-", "").lower(),
                        "source": pair[0],
                        "target": pair[1],
                        "flow_direction": "undirected",
                        "relation": "process_pipe",
                        "confidence": 0.85,
                        "source_page": page,
                        "source_bbox": _source_bbox_for_path(unique_points)
                        if unique_points
                        else [0, 0, 0, 0],
                    }
                )

    return edges, junction_nodes, unresolved_equipment


def build_process_graph(
    equipment: List[Dict[str, Any]],
    audit_tags: List[Dict[str, Any]],
    drawing_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Construct process topology only from legend-classified source pipe geometry.
    """
    nodes = _build_equipment_nodes(equipment, audit_tags)
    graph = nx.Graph()
    for node in nodes:
        graph.add_node(node["tag"], **node)

    edges, junction_nodes, unresolved_equipment = _build_geometry_edges(
        nodes, drawing_evidence
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
    """Keep graph status honest when a user resolves a visual clarification."""
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
        "Ambiguity %s resolved as '%s' → integrity=%s",
        item_id,
        selected_option,
        integrity,
    )

    return {"kpis": kpis, "edges": updated_edges}
