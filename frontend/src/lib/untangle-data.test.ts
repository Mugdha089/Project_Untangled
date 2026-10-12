import { describe, it, expect } from 'vitest';
import { metrics, auditTags, clarifications, resolveQueue } from './untangle-data';
describe('UNTANGLE sample project', () => {
  it('has 142 of 145 matched tags with 97.9 percent completeness', () => {
    expect(metrics.matched).toBe(142); expect(metrics.total).toBe(145);
    expect((metrics.matched / metrics.total * 100).toFixed(1)).toBe('97.9');
  });
  it('retains all 12 equipment items', () => { expect(metrics.retained).toBe(12); expect(metrics.equipmentTotal).toBe(12); });
  it('has 100 percent integrity and no changed edges', () => { expect(metrics.integrity).toBe(100); expect(metrics.changedEdges).toBe(0); });
  it('reports 2.84 seconds of processing', () => { expect(metrics.seconds).toBe(2.84); });
  it('keeps LT-309 missing and XV-104 pending', () => { expect(auditTags.find(t => t.tag === 'LT-309')?.status).toBe('missing'); expect(auditTags.find(t => t.tag === 'XV-104')?.status).toBe('pending'); });
  it('starts with three clarifications and 92 percent recommendation confidence', () => { expect(clarifications).toHaveLength(3); expect(clarifications[0]?.confidence).toBe(92); });
  it('removes an applied clarification but keeps unresolved items flagged', () => {
    expect(resolveQueue(clarifications, '4', 'bridge').map(q => q.id)).toEqual(['7', '11']);
    expect(resolveQueue(clarifications, '4', 'unresolved')).toHaveLength(3);
  });
});