import { describe, it, expect } from 'vitest';
import { mapGraphEdges, mapKpis, metrics, auditTags, clarifications, resolveQueue } from './untangle-data';
describe('UNTANGLE sample project', () => {
  it('has 142 of 145 matched tags with 97.9 percent completeness', () => {
    expect(metrics.matched).toBe(142); expect(metrics.total).toBe(145);
    expect((metrics.matched / metrics.total * 100).toFixed(1)).toBe('97.9');
  });
  it('retains all 12 equipment items', () => { expect(metrics.retained).toBe(12); expect(metrics.equipmentTotal).toBe(12); });
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
  it('removes an applied clarification but keeps unresolved items flagged', () => {
    expect(resolveQueue(clarifications, '4', 'bridge').map(q => q.id)).toEqual(['7', '11']);
    expect(resolveQueue(clarifications, '4', 'unresolved')).toHaveLength(3);
  });
});