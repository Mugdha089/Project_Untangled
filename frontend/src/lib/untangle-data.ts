import type {
  BackendClarificationItem,
  BackendEquipmentNode,
  BackendKpiSummary,
  BackendProcessEdge,
  BackendTagAuditItem,
  ProcessPidResponse,
} from './untangle-api';

export type EquipmentId = string;
export type AuditStatus = 'matched' | 'missing' | 'pending';

export interface AuditTag {
  tag: string;
  type: string;
  bounds: string;
  row: number;
  status: AuditStatus;
  equipment: EquipmentId;
}

export interface WorkspaceMetrics {
  matched: number;
  total: number;
  retained: number;
  equipmentTotal: number;
  integrity: number | null;
  changedEdges: number;
  seconds: number;
  graphIntegrityLabel: string;
}

export interface GraphNodeView {
  id: EquipmentId;
  name: string;
  kind: string;
  tags: string;
  dutyStandby: boolean;
  label: string;
  sourceBounds?: number[];
  sourcePage?: number;
}

export interface GraphEdgeView {
  id: string;
  source: EquipmentId;
  target: EquipmentId;
  confidence: number;
  flowDirection?: string;
  sourceBounds?: number[];
  sourcePage?: number;
}

export interface ClarificationView {
  id: string;
  near: string;
  tag: string;
  confidence: number;
  question: string;
  options: string[];
  defaultRecommendation: string;
  status: string;
}

export type Resolution = 'junction' | 'bridge' | 'unresolved';

export const metrics: WorkspaceMetrics = {
  matched: 142,
  total: 145,
  retained: 12,
  equipmentTotal: 12,
  integrity: null,
  changedEdges: 0,
  seconds: 2.84,
  graphIntegrityLabel: 'Sample topology; not validated against a source drawing',
};

export const auditTags: AuditTag[] = [
  { tag: 'PT-101', type: 'Pressure Transmitter', bounds: '[120, 240, 180, 310]', row: 14, status: 'matched', equipment: 'TK-101' },
  { tag: 'FT-202', type: 'Flow Transmitter', bounds: '[450, 110, 510, 160]', row: 22, status: 'matched', equipment: 'E-102' },
  { tag: 'LT-309', type: 'Level Transmitter', bounds: 'Not Detected', row: 88, status: 'missing', equipment: 'V-102' },
  { tag: 'XV-104', type: 'Solenoid Valve', bounds: 'Ambiguous Cross', row: 102, status: 'pending', equipment: 'P-101' },
];

export const clarifications: ClarificationView[] = [
  {
    id: '4',
    near: 'Pump P-101A',
    tag: 'XV-104',
    confidence: 92,
    question: 'At Pipe Intersection #04 (Near Pump P-101A), do these process lines form a connected junction or a crossing bridge?',
    options: [
      'Connected Junction (4-Way Tee)',
      'Non-connecting Crossover Bridge',
      'Unresolved / Keep Flagged',
    ],
    defaultRecommendation: 'Non-connecting Crossover Bridge',
    status: 'pending',
  },
  {
    id: '7',
    near: 'Heat Exchanger E-102',
    tag: 'FT-202',
    confidence: 89,
    question: 'Is FT-202 associated with the process outlet of E-102 or a parallel bypass line?',
    options: ['Process outlet of E-102', 'Parallel bypass line', 'Unresolved / Keep Flagged'],
    defaultRecommendation: 'Process outlet of E-102',
    status: 'pending',
  },
  {
    id: '11',
    near: 'Vessel V-102',
    tag: 'LV-102',
    confidence: 86,
    question: 'Does LV-102 control the outlet of V-102 or a secondary drain leg?',
    options: ['Outlet of V-102', 'Secondary drain leg', 'Unresolved / Keep Flagged'],
    defaultRecommendation: 'Outlet of V-102',
    status: 'pending',
  },
];

export const defaultGraphNodes: GraphNodeView[] = [
  { id: 'TK-101', name: 'Tank', kind: 'tank', tags: 'PT-101 · LT-101', dutyStandby: false, label: 'Tank TK-101' },
  { id: 'P-101', name: 'Pump pair', kind: 'pump', tags: 'FT-101 · XV-104', dutyStandby: true, label: 'Duty/Standby Pump Pair' },
  { id: 'E-102', name: 'Heat exchanger', kind: 'exchanger', tags: 'FT-202 · TT-102', dutyStandby: false, label: 'Heat Exchanger E-102' },
  { id: 'V-102', name: 'Vessel', kind: 'vessel', tags: 'PT-102 · LV-102', dutyStandby: false, label: 'Outlet Vessel V-102' },
];

export const defaultGraphEdges: GraphEdgeView[] = [
  { id: 'edge_tk101_p101', source: 'TK-101', target: 'P-101', confidence: 0.94 },
  { id: 'edge_p101_e102', source: 'P-101', target: 'E-102', confidence: 0.94 },
  { id: 'edge_e102_v102', source: 'E-102', target: 'V-102', confidence: 0.94 },
];

export function resolveQueue(
  queue: ClarificationView[],
  id: string,
  resolution: Resolution | string,
): ClarificationView[] {
  const keep =
    resolution === 'unresolved' ||
    String(resolution).toLowerCase().includes('unresolved') ||
    String(resolution).toLowerCase().includes('flagged');
  return keep ? queue : queue.filter(item => item.id !== id);
}

export function mapBackendStatus(status: string): AuditStatus {
  if (status === 'Matched') return 'matched';
  if (status === 'Missing in P&ID') return 'missing';
  return 'pending';
}

export function formatBBox(bbox: number[], status: AuditStatus): string {
  if (status === 'missing' || !bbox || bbox.every(v => v === 0)) return 'Not Detected';
  if (status === 'pending') return `Ambiguous · [${bbox.join(', ')}]`;
  return `[${bbox.join(', ')}]`;
}

function inferEquipmentForTag(tag: BackendTagAuditItem, nodes: BackendEquipmentNode[]): EquipmentId {
  const parent = nodes.find(n => n.collapsed_tags.includes(tag.tag_name));
  if (parent) return parent.tag;
  if (nodes.length) return nodes[0]!.tag;
  return 'TK-101';
}

export function mapKpis(kpis: BackendKpiSummary): WorkspaceMetrics {
  const integrityMatch = kpis.graph_integrity.match(/(\d+)\s*%/);
  const integrity = integrityMatch ? Number(integrityMatch[1]) : null;
  const changedMatch = kpis.graph_integrity.match(/(\d+)\s+changed/i);
  return {
    matched: kpis.matched_tags,
    total: kpis.total_tags,
    retained: kpis.retained_equipment,
    equipmentTotal: kpis.retained_equipment,
    integrity,
    changedEdges: changedMatch ? Number(changedMatch[1]) : 0,
    seconds: Number(kpis.processing_time_seconds.toFixed(2)),
    graphIntegrityLabel: kpis.graph_integrity,
  };
}

export function mapAuditTags(
  rows: BackendTagAuditItem[],
  nodes: BackendEquipmentNode[],
): AuditTag[] {
  return rows.map(row => {
    const status = mapBackendStatus(row.status);
    return {
      tag: row.tag_name,
      type: row.type,
      bounds: formatBBox(row.source_bbox, status),
      row: row.excel_row,
      status,
      equipment: inferEquipmentForTag(row, nodes),
    };
  });
}

export function mapGraphNodes(nodes: BackendEquipmentNode[]): GraphNodeView[] {
  return nodes.map(node => ({
    id: node.tag,
    name: node.label.replace(node.tag, '').replace(/[()]/g, '').trim() || node.type,
    kind: node.type,
    tags: node.collapsed_tags.length ? node.collapsed_tags.join(' · ') : '—',
    dutyStandby: node.duty_standby,
    label: node.label,
    sourceBounds: node.source_symbol_bbox ?? node.source_bbox,
    sourcePage: node.source_page,
  }));
}

export function mapGraphEdges(edges: BackendProcessEdge[]): GraphEdgeView[] {
  return edges.map(edge => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    confidence: edge.confidence,
    flowDirection: edge.flow_direction,
    sourceBounds: edge.source_bbox ?? undefined,
    sourcePage: edge.source_page ?? undefined,
  }));
}

export function mapClarifications(items: BackendClarificationItem[]): ClarificationView[] {
  return items.map(item => {
    const nearMatch = item.location_label.match(/near\s+(.+)$/i);
    const tagMatch = item.question.match(/\b([A-Z]{1,4}-\d{2,4}[A-Z]?)\b/);
    return {
      id: item.id,
      near: nearMatch?.[1] ?? item.location_label,
      tag: tagMatch?.[1] ?? item.id,
      confidence: 90,
      question: item.question,
      options: item.options,
      defaultRecommendation: item.default_recommendation,
      status: item.status,
    };
  });
}

export function mapProcessResponse(data: ProcessPidResponse) {
  return {
    metrics: mapKpis(data.kpis),
    auditTags: mapAuditTags(data.tag_audit, data.nodes),
    graphNodes: mapGraphNodes(data.nodes),
    graphEdges: mapGraphEdges(data.edges),
    clarifications: mapClarifications(data.clarification_queue),
    pdfPageCount: data.pdf_page_count,
  };
}

export function resolutionToOption(item: ClarificationView, resolution: Resolution): string {
  const options = item.options;
  if (resolution === 'unresolved') {
    return options.find(o => /unresolved|flagged|not sure/i.test(o)) ?? 'Unresolved / Keep Flagged';
  }
  if (resolution === 'junction') {
    return (
      options.find(o => /junction|connect|tee/i.test(o) && !/non-connecting|crossover|bridge/i.test(o)) ??
      options[0] ??
      'Connected Junction (4-Way Tee)'
    );
  }
  return (
    options.find(o => o === item.defaultRecommendation) ??
    options.find(o => /crossover|bridge|non-connecting/i.test(o)) ??
    item.defaultRecommendation
  );
}
