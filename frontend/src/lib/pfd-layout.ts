import type { GraphEdgeView, GraphNodeView } from "./untangle-data";

export interface PfdPositionedNode extends GraphNodeView {
  x: number;
  y: number;
  radius: number;
}

export interface PfdRoute {
  edge: GraphEdgeView;
  path: string;
  recycle: boolean;
}

export interface PfdLayout {
  width: number;
  height: number;
  nodes: PfdPositionedNode[];
  routes: PfdRoute[];
}

const COLUMN_GAP = 142;
const BASE_ROW_GAP = 164;
const MARGIN_X = 72;
const MARGIN_Y = 86;
const SYMBOL_RADIUS = 34;
const JUNCTION_RADIUS = 7;

function center(bounds: number[] | undefined, index: 0 | 1): number | null {
  if (!bounds || bounds.length !== 4 || !bounds.every(Number.isFinite)) return null;
  return (bounds[index]! + bounds[index + 2]!) / 2;
}

function nodeRadius(node: GraphNodeView): number {
  return node.kind === "junction" ? JUNCTION_RADIUS : SYMBOL_RADIUS;
}

function makeColumns(nodes: GraphNodeView[]): GraphNodeView[][] {
  const positioned = nodes
    .map((node, order) => ({ node, order, x: center(node.sourceBounds, 0) }))
    .filter((item): item is { node: GraphNodeView; order: number; x: number } => item.x !== null)
    .sort((a, b) => a.x - b.x || a.order - b.order);
  if (positioned.length !== nodes.length) return [nodes];

  const columns: GraphNodeView[][] = [];
  let lastSourceX = Number.NEGATIVE_INFINITY;
  for (const item of positioned) {
    if (item.x - lastSourceX > 28 || columns.length === 0) columns.push([]);
    columns[columns.length - 1]!.push(item.node);
    lastSourceX = item.x;
  }
  return columns;
}

function makeRows(nodes: GraphNodeView[]): GraphNodeView[][] {
  const positioned = nodes
    .map((node, order) => ({ node, order, y: center(node.sourceBounds, 1) }))
    .filter((item): item is { node: GraphNodeView; order: number; y: number } => item.y !== null)
    .sort((a, b) => a.y - b.y || a.order - b.order);
  const ordered =
    positioned.length === nodes.length
      ? positioned.map((item) => item.node)
      : [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  return ordered.map((node) => [node]);
}

function orientWithoutSourceCoordinates(
  nodes: GraphNodeView[],
  edges: GraphEdgeView[],
): GraphNodeView[][] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const neighbors = new Map(nodes.map((node) => [node.id, new Set<string>()]));
  for (const edge of edges) {
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue;
    neighbors.get(edge.source)!.add(edge.target);
    neighbors.get(edge.target)!.add(edge.source);
  }

  const visited = new Set<string>();
  const componentColumns: GraphNodeView[][] = [];
  for (const node of nodes) {
    if (visited.has(node.id)) continue;
    const component: GraphNodeView[] = [];
    const queue = [node.id];
    visited.add(node.id);
    while (queue.length) {
      const current = queue.shift()!;
      component.push(byId.get(current)!);
      for (const neighbor of neighbors.get(current) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }

    const ends = component.filter((candidate) => (neighbors.get(candidate.id)?.size ?? 0) <= 1);
    const start = ends[0] ?? component[0]!;
    const depth = new Map<string, number>([[start.id, 0]]);
    const breadthFirst = [start.id];
    while (breadthFirst.length) {
      const current = breadthFirst.shift()!;
      for (const neighbor of neighbors.get(current) ?? []) {
        if (!depth.has(neighbor)) {
          depth.set(neighbor, depth.get(current)! + 1);
          breadthFirst.push(neighbor);
        }
      }
    }
    const maxDepth = Math.max(...Array.from(depth.values()), 0);
    for (let index = 0; index <= maxDepth; index += 1) {
      const column = component
        .filter((candidate) => depth.get(candidate.id) === index)
        .sort((a, b) => a.id.localeCompare(b.id));
      if (column.length) componentColumns.push(column);
    }
  }
  return componentColumns;
}

function makeNodePositions(
  nodes: GraphNodeView[],
  edges: GraphEdgeView[],
): { nodes: PfdPositionedNode[]; width: number; height: number } {
  const hasSourceCoordinates =
    nodes.length > 0 &&
    new Set(nodes.map((node) => node.sourcePage ?? 0)).size === 1 &&
    nodes.every(
      (node) => center(node.sourceBounds, 0) !== null && center(node.sourceBounds, 1) !== null,
    );
  const columns = hasSourceCoordinates
    ? makeColumns(nodes)
    : orientWithoutSourceCoordinates(nodes, edges);
  const rowsByColumn = columns.map((column) => makeRows(column));
  const maxRows = Math.max(1, ...rowsByColumn.map((rows) => rows.length));
  const maxTagRows = Math.max(0, ...nodes.map((node) =>
    node.tags === "—" ? 0 : node.tags.split(" · ").filter(Boolean).length,
  ));
  const rowGap = Math.max(BASE_ROW_GAP, 150 + Math.max(0, maxTagRows - 1) * 14);
  const width = Math.max(640, MARGIN_X * 2 + Math.max(0, columns.length - 1) * COLUMN_GAP);
  const height = Math.max(360, MARGIN_Y * 2 + Math.max(0, maxRows - 1) * rowGap + 130);
  const positioned: PfdPositionedNode[] = [];

  rowsByColumn.forEach((rows, columnIndex) => {
    const columnX = MARGIN_X + columnIndex * COLUMN_GAP;
    rows.forEach((row, rowIndex) => {
      const rowOffset = (rowIndex - (rows.length - 1) / 2) * rowGap;
      row.forEach((node) => {
        positioned.push({
          ...node,
          x: columnX,
          y: height / 2 + rowOffset,
          radius: nodeRadius(node),
        });
      });
    });
  });
  const originalOrder = new Map(nodes.map((node, index) => [node.id, index]));
  positioned.sort((a, b) => originalOrder.get(a.id)! - originalOrder.get(b.id)!);
  return { nodes: positioned, width, height };
}

function segmentIntersectsNode(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  node: PfdPositionedNode,
): boolean {
  const horizontalClearance = node.kind === "junction" ? 20 : 66;
  const topClearance = node.kind === "junction" ? 66 : 68;
  const bottomClearance = node.kind === "junction" ? 16 : 84;
  if (Math.abs(y1 - y2) < 0.01) {
    if (y1 <= node.y - topClearance || y1 >= node.y + bottomClearance) return false;
    return (
      Math.max(Math.min(x1, x2), node.x - horizontalClearance) <
      Math.min(Math.max(x1, x2), node.x + horizontalClearance)
    );
  }
  if (Math.abs(x1 - x2) < 0.01) {
    if (Math.abs(x1 - node.x) >= horizontalClearance) return false;
    return (
      Math.max(Math.min(y1, y2), node.y - topClearance) <
      Math.min(Math.max(y1, y2), node.y + bottomClearance)
    );
  }
  return false;
}

function routeAvoidingNodes(
  source: PfdPositionedNode,
  target: PfdPositionedNode,
  nodes: PfdPositionedNode[],
  width: number,
  height: number,
  outerLane: number | null,
): string {
  const sourceRadius = source.radius + 4;
  const targetRadius = target.radius + 4;
  const leftToRight = source.x <= target.x;
  const startX = source.x + (leftToRight ? sourceRadius : -sourceRadius);
  const endX = target.x + (leftToRight ? -targetRadius : targetRadius);
  const xCandidates = [
    (startX + endX) / 2,
    Math.min(startX, endX) - 24,
    Math.max(startX, endX) + 24,
  ];
  const yCandidates =
    outerLane === null ? [null, 46, height - 46] : [outerLane, outerLane - 24, outerLane + 24];

  for (const laneY of yCandidates) {
    for (const middleX of xCandidates) {
      const points: [number, number][] =
        laneY === null
          ? [
              [startX, source.y],
              [middleX, source.y],
              [middleX, target.y],
              [endX, target.y],
            ]
          : [
              [startX, source.y],
              [startX, laneY],
              [endX, laneY],
              [endX, target.y],
            ];
      const blocked = nodes.some((node) => {
        if (node.id === source.id || node.id === target.id) return false;
        return points.some((point, index) => {
          const next = points[index + 1];
          return next ? segmentIntersectsNode(point[0], point[1], next[0], next[1], node) : false;
        });
      });
      if (!blocked) {
        return points
          .map((point, index) => `${index === 0 ? "M" : "L"}${point[0]} ${point[1]}`)
          .join(" ");
      }
    }
  }

  const laneY = outerLane ?? Math.min(source.y, target.y) - 80;
  return `M${startX} ${source.y} L${startX} ${laneY} L${endX} ${laneY} L${endX} ${target.y}`;
}

function cycleEdges(edges: GraphEdgeView[]): Set<string> {
  const cyclic = new Set<string>();
  const adjacency = new Map<string, Set<string>>();
  for (const edge of edges) {
    adjacency.set(edge.source, (adjacency.get(edge.source) ?? new Set()).add(edge.target));
    adjacency.set(edge.target, (adjacency.get(edge.target) ?? new Set()).add(edge.source));
  }
  for (const edge of edges) {
    const visited = new Set([edge.source]);
    const queue = [edge.source];
    while (queue.length) {
      const current = queue.shift()!;
      for (const neighbor of adjacency.get(current) ?? []) {
        if (
          (current === edge.source && neighbor === edge.target) ||
          (current === edge.target && neighbor === edge.source)
        )
          continue;
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
    if (visited.has(edge.target)) cyclic.add(edge.id);
  }
  return cyclic;
}

function selectRecycleRoute(edges: GraphEdgeView[], nodes: PfdPositionedNode[]): string | null {
  const cyclic = cycleEdges(edges);
  if (!cyclic.size) return null;
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const candidates = edges.filter((edge) => cyclic.has(edge.id));
  candidates.sort((a, b) => {
    const aBounds = a.sourceBounds;
    const bBounds = b.sourceBounds;
    const aLength =
      aBounds?.length === 4
        ? Math.abs(aBounds[2]! - aBounds[0]!) + Math.abs(aBounds[3]! - aBounds[1]!)
        : 0;
    const bLength =
      bBounds?.length === 4
        ? Math.abs(bBounds[2]! - bBounds[0]!) + Math.abs(bBounds[3]! - bBounds[1]!)
        : 0;
    return bLength - aLength || a.id.localeCompare(b.id);
  });
  return candidates[0] && nodeById.has(candidates[0].source) && nodeById.has(candidates[0].target)
    ? candidates[0].id
    : null;
}

export function layoutPfd(nodes: GraphNodeView[], edges: GraphEdgeView[]): PfdLayout {
  const positioned = makeNodePositions(nodes, edges);
  const nodeById = new Map(positioned.nodes.map((node) => [node.id, node]));
  const recycleRoute = selectRecycleRoute(edges, positioned.nodes);
  const routes = edges.flatMap((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target || source.id === target.id) return [];
    const outerLane = edge.id === recycleRoute ? 52 : null;
    return [
      {
        edge,
        path: routeAvoidingNodes(
          source,
          target,
          positioned.nodes,
          positioned.width,
          positioned.height,
          outerLane,
        ),
        recycle: edge.id === recycleRoute,
      },
    ];
  });
  return { ...positioned, routes };
}
