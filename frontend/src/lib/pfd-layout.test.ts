import { describe, expect, it } from "vitest";
import { layoutPfd } from "./pfd-layout";
import type { GraphEdgeView, GraphNodeView } from "./untangle-data";

function node(id: string, kind = "pump", x?: number, y?: number, tags = ""): GraphNodeView {
  return {
    id,
    name: kind === "junction" ? "Junction" : `${kind} equipment`,
    kind,
    tags,
    dutyStandby: false,
    label: id,
    ...(x === undefined || y === undefined
      ? {}
      : { sourceBounds: [x - 8, y - 8, x + 8, y + 8], sourcePage: 0 }),
  };
}

function edge(id: string, source: string, target: string, sourceBounds?: number[]): GraphEdgeView {
  return { id, source, target, confidence: 1, flowDirection: "undirected", sourceBounds };
}

function pathSegments(path: string): number[][] {
  return Array.from(path.matchAll(/[-\d.]+/g), (match) => Number(match[0])).reduce<number[][]>(
    (segments, value, index, values) => {
      if (index % 2 === 0 && index + 1 < values.length) {
        segments.push([value, values[index + 1]!]);
      }
      return segments;
    },
    [],
  );
}

function routeHitsNode(
  path: string,
  candidate: GraphNodeView & { x: number; y: number; radius: number },
) {
  const points = pathSegments(path);
  return points.some((point, index) => {
    const next = points[index + 1];
    if (!next) return false;
    const horizontalClearance = candidate.kind === "junction" ? 20 : 66;
    const topClearance = candidate.kind === "junction" ? 66 : 68;
    const bottomClearance = candidate.kind === "junction" ? 16 : 84;
    if (
      point[1] === next[1] &&
      point[1]! > candidate.y - topClearance &&
      point[1]! < candidate.y + bottomClearance
    ) {
      return (
        Math.max(Math.min(point[0]!, next[0]!), candidate.x - horizontalClearance) <
        Math.min(Math.max(point[0]!, next[0]!), candidate.x + horizontalClearance)
      );
    }
    if (point[0] === next[0] && Math.abs(point[0]! - candidate.x) < horizontalClearance) {
      return (
        Math.max(Math.min(point[1]!, next[1]!), candidate.y - topClearance) <
        Math.min(Math.max(point[1]!, next[1]!), candidate.y + bottomClearance)
      );
    }
    return false;
  });
}

function labelAreasOverlap(
  first: GraphNodeView & { x: number; y: number },
  second: GraphNodeView & { x: number; y: number },
): boolean {
  const firstHalfWidth = first.kind === "junction" ? 20 : 66;
  const secondHalfWidth = second.kind === "junction" ? 20 : 66;
  const firstTop = first.kind === "junction" ? 66 : 68;
  const secondTop = second.kind === "junction" ? 66 : 68;
  const firstBottom = first.kind === "junction" ? 16 : 84;
  const secondBottom = second.kind === "junction" ? 16 : 84;
  return (
    first.x - firstHalfWidth < second.x + secondHalfWidth &&
    first.x + firstHalfWidth > second.x - secondHalfWidth &&
    first.y - firstTop < second.y + secondBottom &&
    first.y + firstBottom > second.y - secondTop
  );
}

describe("simplified PFD layout", () => {
  it("lays out a linear process left to right without changing equipment or edges", () => {
    const nodes = [
      node("E-3", "exchanger", 300, 120),
      node("TK-1", "tank", 0, 120),
      node("P-2", "pump", 150, 120),
    ];
    const edges = [edge("e2", "P-2", "E-3"), edge("e1", "TK-1", "P-2")];
    const result = layoutPfd(nodes, edges);

    expect(result.nodes.map((item) => item.id)).toEqual(["E-3", "TK-1", "P-2"]);
    expect(result.nodes.find((item) => item.id === "TK-1")!.x).toBeLessThan(
      result.nodes.find((item) => item.id === "P-2")!.x,
    );
    expect(result.nodes.find((item) => item.id === "P-2")!.x).toBeLessThan(
      result.nodes.find((item) => item.id === "E-3")!.x,
    );
    expect(result.routes.map((route) => route.edge.id)).toEqual(["e2", "e1"]);
  });

  it("separates parallel pumps into readable lanes", () => {
    const result = layoutPfd(
      [
        node("P-101A", "pump", 100, 80),
        node("P-101B", "pump", 100, 130),
        node("J-1", "junction", 0, 100),
      ],
      [edge("branch-a", "J-1", "P-101A"), edge("branch-b", "J-1", "P-101B")],
    );
    const pumps = result.nodes.filter((item) => item.kind === "pump");

    expect(pumps[0]!.x).toBe(pumps[1]!.x);
    expect(Math.abs(pumps[0]!.y - pumps[1]!.y)).toBeGreaterThanOrEqual(164);
  });

  it("keeps branch and merge junctions explicit and routes all supporting edges", () => {
    const nodes = [
      node("J-SPLIT", "junction", 0, 100),
      node("P-A", "pump", 100, 60),
      node("P-B", "pump", 100, 140),
      node("J-MERGE", "junction", 200, 100),
    ];
    const edges = [
      edge("split-a", "J-SPLIT", "P-A"),
      edge("split-b", "J-SPLIT", "P-B"),
      edge("merge-a", "P-A", "J-MERGE"),
      edge("merge-b", "P-B", "J-MERGE"),
    ];
    const result = layoutPfd(nodes, edges);

    expect(result.nodes.filter((item) => item.kind === "junction")).toHaveLength(2);
    expect(result.routes).toHaveLength(edges.length);
    expect(result.routes.every((route) => /L/.test(route.path))).toBe(true);
    for (let index = 0; index < result.nodes.length; index += 1) {
      for (const other of result.nodes.slice(index + 1)) {
        expect(labelAreasOverlap(result.nodes[index]!, other)).toBe(false);
      }
    }
    for (const route of result.routes) {
      const endpoints = new Set([route.edge.source, route.edge.target]);
      for (const item of result.nodes) {
        if (!endpoints.has(item.id)) expect(routeHitsNode(route.path, item)).toBe(false);
      }
    }
  });

  it("retains control/utility nodes and source edge evidence without converting tags into nodes", () => {
    const nodes = [node("F-1", "filter", 0, 0, "FT-1 · PT-1"), node("XV-1", "valve", 100, 0)];
    const edgeEvidence = [320, 80, 470, 90];
    const result = layoutPfd(nodes, [edge("control-or-utility", "F-1", "XV-1", edgeEvidence)]);

    expect(result.nodes.map((item) => item.id)).toEqual(["F-1", "XV-1"]);
    expect(result.nodes[0]!.tags).toBe("FT-1 · PT-1");
    expect(result.routes[0]!.edge.sourceBounds).toEqual(edgeEvidence);
  });

  it("routes one recycle edge around the outside of a detected cycle", () => {
    const result = layoutPfd(
      [node("A", "pump", 0, 0), node("B", "filter", 100, 0), node("C", "valve", 200, 0)],
      [
        edge("main-a", "A", "B", [0, 0, 100, 0]),
        edge("main-b", "B", "C", [100, 0, 200, 0]),
        edge("recycle", "A", "C", [0, -100, 200, 0]),
      ],
    );
    const recycle = result.routes.find((route) => route.edge.id === "recycle")!;

    expect(recycle.recycle).toBe(true);
    expect(
      pathSegments(recycle.path).some(
        ([, y]) => y < Math.min(...result.nodes.map((item) => item.y)),
      ),
    ).toBe(true);
  });

  it("does not create a node for a deliberately missing or near-match tag", () => {
    const present = node("P-101", "pump", 0, 0, "FT-101");
    const result = layoutPfd([present], []);

    expect(result.nodes.map((item) => item.id)).toEqual(["P-101"]);
    expect(result.routes).toHaveLength(0);
  });

  it("keeps symbols and labels inside a dynamic canvas and separates adjacent nodes", () => {
    const result = layoutPfd(
      [node("A", "tank", 0, 0), node("B", "filter", 100, 100), node("C", "valve", 200, 0)],
      [edge("ab", "A", "B"), edge("bc", "B", "C")],
    );

    for (const item of result.nodes) {
      expect(item.x - 62).toBeGreaterThanOrEqual(0);
      expect(item.x + 62).toBeLessThan(result.width);
      expect(item.y - 68).toBeGreaterThanOrEqual(0);
      expect(item.y + 82).toBeLessThan(result.height);
    }
    expect(result.width).toBeGreaterThanOrEqual(640);
    expect(result.height).toBeGreaterThanOrEqual(360);
  });
});
