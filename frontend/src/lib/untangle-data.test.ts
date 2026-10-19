import { describe, it, expect } from 'vitest';
import { mapAuditTags, mapBackendStatus, mapClarifications, mapGraphEdges, mapKpis, markTagUserConfirmed, metrics, auditTags, clarifications, resolveQueue } from './untangle-data';
describe('UNTANGLE sample project', () => {
  it('keeps sample tag counters consistent with the visible audit rows', () => {
    expect(metrics.matched).toBe(auditTags.filter(tag => tag.status === 'matched').length);
    expect(metrics.total).toBe(new Set(auditTags.map(tag => tag.tag)).size);
    expect(metrics.auditRows).toBe(auditTags.length);
    expect(metrics.missing).toBe(auditTags.filter(tag => tag.status === 'missing').length);
    expect(metrics.pendingReviewTags).toBe(auditTags.filter(tag => tag.status === 'pending').length);
  });
  it('counts the visible sample graph nodes', () => { expect(metrics.retained).toBe(4); expect(metrics.equipmentTotal).toBe(4); });
  it('does not label the sample topology as source-validated', () => {
    expect(metrics.integrity).toBeNull();
    expect(metrics.graphIntegrityLabel).toContain('not validated');
  });
  it('reports 2.84 seconds of processing', () => { expect(metrics.seconds).toBe(2.84); });
  it('keeps LT-309 missing and XV-104 pending', () => { expect(auditTags.find(t => t.tag === 'LT-309')?.status).toBe('missing'); expect(auditTags.find(t => t.tag === 'XV-104')?.status).toBe('pending'); });
  it('starts with three clarifications and 92 percent recommendation confidence', () => { expect(clarifications).toHaveLength(3); expect(clarifications[0]?.confidence).toBe(92); });
  it('does not convert unverified graph status into 100 percent integrity', () => {
    const result = mapKpis({
      total_tags: 2,
      matched_tags: 2,
      retained_equipment: 2,
      graph_integrity: 'Unverified — no legend-classified process-pipe geometry was found.',
      processing_time_seconds: 0.4,
    });
    expect(result.integrity).toBeNull();
    expect(result.graphIntegrityLabel).toContain('Unverified');
  });
  it('preserves edge source evidence when mapping live graph responses', () => {
    const sourceBounds = [120, 80, 240, 80];
    const [mapped] = mapGraphEdges([{
      id: 'edge-1',
      source: 'P-101',
      target: 'V-101',
      flow_direction: 'undirected',
      relation: 'process_pipe',
      confidence: 0.9,
      source_page: 1,
      source_bbox: sourceBounds,
    }]);
    expect(mapped?.sourceBounds).toEqual(sourceBounds);
    expect(mapped?.sourcePage).toBe(1);
  });
  it('maps vector segment provenance without inventing edge confidence', () => {
    const [mapped] = mapGraphEdges([{
      id: 'edge-2',
      source: 'P-101',
      target: 'V-101',
      flow_direction: 'undirected',
      relation: 'process_pipe',
      evidence_status: 'source_geometry',
      source_segment_ids: ['p0_d3_i0', 'p0_d8_i1'],
    }]);
    expect(mapped?.sourceSegmentIds).toEqual(['p0_d3_i0', 'p0_d8_i1']);
    expect(mapped?.evidenceStatus).toBe('source_geometry');
    expect(mapped?.confidence).toBeUndefined();
  });
  it('does not assign an unsupported audit tag to the first equipment node', () => {
    const [unassociated] = mapAuditTags([{
      tag_name: 'PT-999', type: 'Pressure Transmitter', source_bbox: [10, 20, 30, 40],
      excel_row: 2, status: 'Matched', confidence: 0.9,
    }], [{
      id: 'eq-p1', tag: 'P-1', type: 'pump', label: 'Pump P-1',
      source_bbox: [1, 1, 5, 5], source_page: 0, collapsed_tags: [], duty_standby: false,
    }]);
    expect(unassociated?.equipment).toBeNull();
  });
  it('preserves the workbook sheet for inventory audit provenance', () => {
    const [mapped] = mapAuditTags([{
      tag_name: 'E-609', type: 'Heat exchanger', source_bbox: [0, 0, 0, 0],
      excel_row: 7, excel_rows: [7], excel_sheet: 'Major Equipment',
      excel_sheets: ['Major Equipment'], status: 'Missing in P&ID', confidence: 0,
    }], []);
    expect(mapped?.excelSheets).toEqual(['Major Equipment']);
  });
  it('preserves the source crop and page for evidence-backed clarifications', () => {
    const crop = 'data:image/png;base64,c2FtcGxl';
    const [mapped] = mapClarifications([{
      id: 'crossing_p0_400_300',
      location_label: 'Process line crossing on page 1',
      question: 'The source shows two process strokes crossing. Do they connect at this point?',
      crop_bbox: [364, 264, 436, 336],
      source_page: 0,
      evidence_crop_data_uri: crop,
      default_recommendation: 'Unresolved / Keep Flagged',
      options: ['Connected Junction (4-Way Tee)', 'Crossover / No Connection', 'Unresolved / Keep Flagged'],
      status: 'pending',
    }]);
    expect(mapped?.sourcePage).toBe(0);
    expect(mapped?.evidenceCropDataUri).toBe(crop);
    expect(mapped?.options).toContain('Crossover / No Connection');
  });
  it('removes an applied clarification but keeps unresolved items flagged', () => {
    expect(resolveQueue(clarifications, '4', 'bridge').map(q => q.id)).toEqual(['7', '11']);
    expect(resolveQueue(clarifications, '4', 'unresolved')).toHaveLength(3);
  });
  it('keeps user confirmation distinct from PDF detection and does not invent coordinates', () => {
    const source = [
      { tag: 'LT-309', type: 'Level Transmitter', bounds: 'Not Detected', row: 88, status: 'missing' as const, equipment: 'V-102' },
      { tag: 'PT-101', type: 'Pressure Transmitter', bounds: '[1, 2, 3, 4]', row: 2, status: 'matched' as const, equipment: 'TK-101' },
    ];
    const confirmed = markTagUserConfirmed(source, 'LT-309');
    expect(source[0]?.status).toBe('missing');
    expect(confirmed[0]?.status).toBe('user-confirmed');
    expect(confirmed[0]?.bounds).toContain('bounds unavailable');
    expect(confirmed[0]?.bounds).not.toMatch(/\[\d+,\s*\d+/);
    expect(confirmed[1]?.status).toBe('matched');
  });
  it('retains ambiguous audit status separately from pending review', () => {
    expect(mapBackendStatus('Ambiguous')).toBe('ambiguous');
    expect(mapBackendStatus('Pending Review')).toBe('pending');
  });
  it('maps documented backend count semantics into the workspace metrics', () => {
    const result = mapKpis({
      total_tags: 1,
      matched_tags: 0,
      retained_equipment: 1,
      graph_integrity: 'Unverified',
      processing_time_seconds: 0.1,
      inventory_rows: 3,
      usable_inventory_rows: 2,
      unique_inventory_tags: 1,
      duplicate_inventory_tags: 1,
      duplicate_inventory_rows: 1,
      detected_source_tags: 1,
      missing_tags: 0,
      ambiguous_tags: 1,
      pending_review_tags: 0,
      audit_rows: 1,
      clarification_items: 0,
    });
    expect(result.total).toBe(1);
    expect(result.inventoryRows).toBe(3);
    expect(result.usableInventoryRows).toBe(2);
    expect(result.duplicateInventoryTags).toBe(1);
    expect(result.matched).toBe(0);
    expect(result.ambiguous).toBe(1);
    expect(result.auditRows).toBe(1);
  });
});
