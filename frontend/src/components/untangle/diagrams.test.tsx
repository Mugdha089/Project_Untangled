import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProcessDiagram } from './diagrams';

describe('source-backed process diagram labels', () => {
  it('labels the detected equipment tag once and renders every collapsed instrument tag', () => {
    render(
      <ProcessDiagram
        selected={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
        nodes={[{
          id: 'P-101A', name: 'Pump', kind: 'pump', tags: 'FT-101 · PT-101 · LT-101',
          dutyStandby: true, label: 'Pump P-101A',
        }]}
        edges={[]}
      />,
    );

    expect(screen.getAllByText('P-101A')).toHaveLength(1);
    expect(screen.getByText('FT-101')).toBeInTheDocument();
    expect(screen.getByText('PT-101')).toBeInTheDocument();
    expect(screen.getByText('LT-101')).toBeInTheDocument();
    expect(screen.queryByText('P-101AA / P-101AB')).not.toBeInTheDocument();
  });

  it('shows detected tags in a separate strip without claiming flow when no edge exists', () => {
    render(
      <ProcessDiagram
        selected={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
        nodes={[{
          id: 'P-101', name: 'Pump', kind: 'pump', tags: '—',
          dutyStandby: false, label: 'Pump P-101',
        }]}
        edges={[]}
        sourceTags={[{
          tag: 'FT-101', type: 'Flow Transmitter', bounds: '[10, 20, 30, 40]',
          row: 2, status: 'matched', equipment: null,
        }]}
      />,
    );

    expect(screen.getByText('SOURCE-DETECTED TAGS · NO EQUIPMENT ASSOCIATION INFERRED')).toBeInTheDocument();
    expect(screen.getByText('FT-101')).toBeInTheDocument();
    expect(screen.getByText('NO SOURCE-SUPPORTED FLOW EDGES')).toBeInTheDocument();
    expect(document.querySelector('.source-tag-matched')).toBeInTheDocument();
  });

  it('does not draw a direction arrow for an undirected source edge', () => {
    const { container } = render(
      <ProcessDiagram
        selected={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
        nodes={[
          { id: 'P-101', name: 'Pump', kind: 'pump', tags: '—', dutyStandby: false, label: 'Pump P-101' },
          { id: 'V-101', name: 'Vessel', kind: 'vessel', tags: '—', dutyStandby: false, label: 'Vessel V-101' },
        ]}
        edges={[{
          id: 'pipe-1', source: 'P-101', target: 'V-101', flowDirection: 'undirected',
        }]}
      />,
    );

    expect(container.querySelector('.flow-path')?.getAttribute('marker-end')).toBeNull();
    expect(screen.getByText('FLOW DIRECTION UNRESOLVED')).toBeInTheDocument();
  });

  it('distinguishes provisional nozzle alignments from reviewer-confirmed edges', () => {
    const { container } = render(
      <ProcessDiagram
        selected={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
        nodes={[
          { id: 'P-101', name: 'Pump', kind: 'pump', tags: '—', dutyStandby: false, label: 'Pump P-101' },
          { id: 'V-101', name: 'Vessel', kind: 'vessel', tags: '—', dutyStandby: false, label: 'Vessel V-101' },
        ]}
        edges={[
          { id: 'provisional', source: 'P-101', target: 'V-101', flowDirection: 'undirected', evidenceStatus: 'provisional_nozzle_alignment' },
          { id: 'confirmed', source: 'P-101', target: 'V-101', flowDirection: 'undirected', evidenceStatus: 'user_confirmed_nozzle' },
        ]}
      />,
    );

    const provisional = container.querySelector('path[stroke-dasharray="6 4"]');
    const confirmed = container.querySelector('path[stroke-width="2.5"]');
    expect(provisional?.getAttribute('stroke-dasharray')).toBe('6 4');
    expect(confirmed?.getAttribute('stroke-width')).toBe('2.5');
    const titles = Array.from(
      container.querySelectorAll('title'),
      (title) => title.textContent?.trim(),
    );
    expect(titles).toContain('Provisional equipment connection: aligned nozzle endpoint is awaiting review');
    expect(titles).toContain('Equipment connection confirmed by reviewer');
  });
});
