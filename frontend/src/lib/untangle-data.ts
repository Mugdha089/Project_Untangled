import type {
  BackendClarificationItem,
  BackendEquipmentNode,
  BackendKpiSummary,
  BackendProcessEdge,
  BackendTagAuditItem,
  ProcessPidResponse,
} from './untangle-api';

export type EquipmentId = string;
export type AuditStatus = 'matched' | 'missing' | 'pending' | 'ambiguous' | 'user-confirmed';

export interface AuditTag {
  tag: string;
  type: string;
  bounds: string;
  row: number;
  excelRows?: number[];
  excelSheets?: (string | null)[];
  status: AuditStatus;
  equipment: EquipmentId | null;
  rawText?: string;
  ocrConfidence?: number;
  reason?: string;
}

export interface WorkspaceMetrics {
  matched: number;
  total: number;
  inventoryRows?: number;
  usableInventoryRows?: number;
  duplicateInventoryTags?: number;
  detectedSourceTags?: number;
  missing?: number;
  ambiguous?: number;
  clarificationItems?: number;
  deferredClarificationItems?: number;
  rasterLineCandidates?: number;
  rasterIntersectionCandidates?: number;
  auditRows?: number;
  pendingReviewTags?: number;
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
  confidence?: number;
  evidenceStatus?: string;
  sourceSegmentIds?: string[];
  flowDirection?: string;
  sourceBounds?: number[];
  sourcePage?: number;
}

export interface ClarificationView {
  id: string;
  near: string;
  tag: string;
  confidence?: number;
  question: string;
  options: string[];
  defaultRecommendation: string;
  status: string;
  selectedOption?: string;
  sourcePage?: number;
  evidenceCropDataUri?: string;
}

export type Resolution = 'junction' | 'bridge' | 'unresolved';

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

export const metrics: WorkspaceMetrics = {
  matched: auditTags.filter(tag => tag.status === 'matched').length,
  total: new Set(auditTags.map(tag => tag.tag)).size,
  inventoryRows: auditTags.reduce((count, tag) => count + (tag.excelRows?.length ?? 1), 0),
  usableInventoryRows: auditTags.reduce((count, tag) => count + (tag.excelRows?.length ?? 1), 0),
  duplicateInventoryTags: auditTags.filter(tag => (tag.excelRows?.length ?? 1) > 1).length,
  detectedSourceTags: auditTags.filter(tag => tag.status === 'matched').length,
  missing: auditTags.filter(tag => tag.status === 'missing').length,
  ambiguous: auditTags.filter(tag => tag.status === 'ambiguous').length,
  clarificationItems: clarifications.length,
  auditRows: auditTags.length,
  pendingReviewTags: auditTags.filter(tag => tag.status === 'pending').length,
  retained: defaultGraphNodes.length,
  equipmentTotal: defaultGraphNodes.length,
  integrity: null,
  changedEdges: 0,
  seconds: 2.84,
  graphIntegrityLabel: 'Sample topology; not validated against a source drawing',
};

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
  if (status === 'Ambiguous') return 'ambiguous';
  return 'pending';
}

export function formatBBox(bbox: number[], status: AuditStatus): string {
  if (status === 'user-confirmed') return 'User-confirmed · source bounds unavailable';
  if (status === 'missing' || !bbox || bbox.every(v => v === 0)) return 'Not Detected';
  if (status === 'pending' || status === 'ambiguous') return `Ambiguous · [${bbox.join(', ')}]`;
  return `[${bbox.join(', ')}]`;
}

export function markTagUserConfirmed(rows: AuditTag[], tagName: string): AuditTag[] {
  return rows.map(row => row.tag === tagName
    && row.status === 'missing'
    ? { ...row, status: 'user-confirmed', bounds: 'User-confirmed · source bounds unavailable' }
    : row);
}

function inferEquipmentForTag(tag: BackendTagAuditItem, nodes: BackendEquipmentNode[]): EquipmentId | null {
  const parent = nodes.find(n => n.collapsed_tags.includes(tag.tag_name));
  return parent?.tag ?? null;
}

export function mapKpis(kpis: BackendKpiSummary): WorkspaceMetrics {
  const integrityMatch = kpis.graph_integrity.match(/(\d+)\s*%/);
  const integrity = integrityMatch ? Number(integrityMatch[1]) : null;
  const changedMatch = kpis.graph_integrity.match(/(\d+)\s+changed/i);
  return {
    matched: kpis.matched_tags,
    total: kpis.unique_inventory_tags ?? kpis.total_tags,
    inventoryRows: kpis.inventory_rows ?? kpis.total_tags,
    usableInventoryRows: kpis.usable_inventory_rows ?? kpis.total_tags,
    duplicateInventoryTags: kpis.duplicate_inventory_tags ?? 0,
    detectedSourceTags: kpis.detected_source_tags ?? kpis.matched_tags,
    missing: kpis.missing_tags ?? Math.max(0, kpis.total_tags - kpis.matched_tags),
    ambiguous: kpis.ambiguous_tags ?? 0,
    clarificationItems: kpis.clarification_items ?? 0,
    deferredClarificationItems: kpis.deferred_clarification_items ?? 0,
    rasterLineCandidates: kpis.raster_line_candidates ?? 0,
    rasterIntersectionCandidates: kpis.raster_intersection_candidates ?? 0,
    auditRows: kpis.audit_rows ?? kpis.total_tags,
    pendingReviewTags: kpis.pending_review_tags ?? 0,
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
      excelRows: row.excel_rows ?? (row.excel_row > 0 ? [row.excel_row] : []),
      excelSheets: row.excel_sheets ?? (row.excel_sheet ? [row.excel_sheet] : []),
      status,
      equipment: inferEquipmentForTag(row, nodes),
      ...(row.raw_text != null ? { rawText: row.raw_text } : {}),
      ...(row.ocr_confidence != null ? { ocrConfidence: row.ocr_confidence } : {}),
      ...(row.reason ? { reason: explainAuditReason(row.reason) } : {}),
    };
  });
}

function explainAuditReason(reason: string): string {
  const explanations: Record<string, string> = {
    software_derived_record: "Software-derived record; not a physical P&ID symbol.",
    source_visibility_unverified:
      "Workbook metadata does not establish that this record should appear as a physical symbol.",
    source_page_mapping_unverified:
      "The workbook P&ID reference is not mapped to a verified source page; missing status is deferred.",
    no_valid_source_detection: "No valid source-located tag detection was found.",
    duplicate_inventory_tag:
      "Duplicate Excel rows: one PDF detection cannot confirm multiple inventory rows.",
    low_ocr_confidence:
      "OCR confidence is below the review threshold; verify the source crop.",
    duplicate_source_detection:
      "Repeated source detections are ambiguous; review the OCR evidence.",
    ambiguous_pdf_detection: "The source reading is ambiguous and needs review.",
    unmatched_pdf_detection: "Detected PDF tag is not present in the Excel inventory.",
  };
  return explanations[reason] ?? reason.replaceAll("_", " ");
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
    ...(edge.confidence != null ? { confidence: edge.confidence } : {}),
    ...(edge.evidence_status ? { evidenceStatus: edge.evidence_status } : {}),
    ...(edge.source_segment_ids
      ? { sourceSegmentIds: edge.source_segment_ids }
      : {}),
    flowDirection: edge.flow_direction,
    ...(edge.source_bbox ? { sourceBounds: edge.source_bbox } : {}),
    ...(edge.source_page != null ? { sourcePage: edge.source_page } : {}),
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
      question: item.question,
      options: item.options,
      defaultRecommendation: item.default_recommendation,
      status: item.status,
        ...(item.confidence != null ? { confidence: item.confidence } : {}),
      ...(item.selected_option ? { selectedOption: item.selected_option } : {}),
      ...(item.source_page != null ? { sourcePage: item.source_page } : {}),
      ...(item.evidence_crop_data_uri
        ? { evidenceCropDataUri: item.evidence_crop_data_uri }
        : {}),
    };
  });
}

export function mapProcessResponse(data: ProcessPidResponse) {
  return {
    runId: data.run_id,
    pdfFilename: data.pdf_filename,
    excelFilename: data.excel_filename,
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
