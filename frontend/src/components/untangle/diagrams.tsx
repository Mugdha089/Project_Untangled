import { useEffect, useRef, useState } from 'react';
import type { EquipmentId, GraphEdgeView, GraphNodeView } from '@/lib/untangle-data';
import { layoutPfd } from '@/lib/pfd-layout';

type PfdZoom = 'auto' | 'fit' | number;

interface DiagramProps {
  selected: EquipmentId | null;
  onSelect: (id: EquipmentId) => void;
  onHover: (id: EquipmentId | null) => void;
}

export function EquipmentSymbol({ kind, x = 0, y = 0 }: { kind: string; x?: number; y?: number }) {
  const symbol = kind === 'tank' || kind === 'pump' || kind === 'mixer' || kind === 'exchanger' || kind === 'vessel' || kind === 'valve' || kind === 'filter' || kind === 'junction' ? kind : 'pump';
  return (
    <g transform={`translate(${x},${y})`} className="equipment-symbol" fill="none" stroke="currentColor" strokeWidth="1.8">
      {symbol === 'tank' && (
        <>
          <path d="M-23-27 Q0-39 23-27 V25 Q0 37-23 25Z" />
          <path d="M-23-27 Q0-15 23-27 M-23 25 Q0 13 23 25 M-14 31v8 M14 31v8" />
          <path d="M-23 5h46" strokeDasharray="3 3" />
        </>
      )}
      {symbol === 'pump' && (
        <>
          <circle r="22" />
          <path d="M-9-12 L14 0-9 12Z M-17 17-25 30h50l-8-13" />
          <path d="M-31 0h9 M22 0h9" />
        </>
      )}
      {symbol === 'mixer' && (
        <>
          <circle r="22" />
          <path d="M0-22v12 M0-10l-12-8 M0-10l12-8 M0-10v23 M-14 13h28" />
          <path d="M-18 22h36" />
        </>
      )}
      {symbol === 'exchanger' && (
        <>
          <circle r="27" />
          <path d="M-27 0h10l8-15 15 30 9-15h12 M-15-22v-12 M15 22v12" />
        </>
      )}
      {symbol === 'vessel' && (
        <path d="M-19-22 C-19-40 19-40 19-22 V22 C19 40-19 40-19 22Z M-19-20h38 M-19 20h38 M-12 34v7 M12 34v7" />
      )}
      {symbol === 'valve' && <path d="M-14-10L14 10V-10L-14 10Z" />}
      {symbol === 'filter' && (
        <>
          <rect x="-24" y="-18" width="48" height="36" rx="3" />
          <path d="M-15-10l30 20 M-15 0l20 13 M-5-13l20 13" />
        </>
      )}
      {symbol === 'junction' && <circle r="5" fill="currentColor" />}
    </g>
  );
}

export function ProcessDiagram({
  selected,
  onSelect,
  onHover,
  topology = false,
  nodes,
  edges,
  zoom = 'auto',
  onLayoutScaleChange,
}: DiagramProps & {
  topology?: boolean;
  nodes: GraphNodeView[];
  edges: GraphEdgeView[];
  zoom?: PfdZoom;
  onLayoutScaleChange?: (fitScale: number, autoScale: number) => void;
}) {
  const layout = layoutPfd(nodes, edges);
  const byId = new Map(layout.nodes.map(node => [node.id, node]));
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 640, height: 371 });
  useEffect(() => {
    const canvas = svgRef.current?.closest('.pfd-canvas');
    if (!canvas || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setCanvasSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);
  const fitScale = Math.min(1, canvasSize.width / layout.width, canvasSize.height / layout.height);
  const autoScale = layout.width > 900 ? 1 : fitScale;
  useEffect(() => {
    onLayoutScaleChange?.(fitScale, autoScale);
  }, [autoScale, fitScale, onLayoutScaleChange]);
  const scale = zoom === 'auto'
    ? autoScale
    : zoom === 'fit'
      ? fitScale
      : zoom / 100;
  const diagramWidth = layout.width * scale;
  const diagramHeight = layout.height * scale;
  const equipmentCount = layout.nodes.filter(node => node.kind !== 'junction').length;

  return (
    <div className="pfd-diagram" style={{ width: diagramWidth, height: diagramHeight }}>
      <svg
        ref={svgRef}
        id="process-diagram"
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="process-svg"
        role="img"
        aria-label={topology ? 'Full process topology graph' : 'Simplified process flow diagram'}
      >
      <defs>
        <marker id="flow-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0 0L7 3.5 0 7" className="arrow-fill" />
        </marker>
        <pattern id="pfd-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r=".65" className="grid-dot" />
        </pattern>
      </defs>
      <rect width={layout.width} height={layout.height} className="diagram-bg" />
      <rect width={layout.width} height={layout.height} fill="url(#pfd-grid)" />
      <text x="25" y="32" className="diagram-eyebrow">
        {topology
          ? `SOURCE GEOMETRY TOPOLOGY / ${layout.nodes.length} NODES`
          : 'PROCESS CONNECTIONS / SOURCE GEOMETRY'}
      </text>
      <text x={layout.width - 25} y="32" textAnchor="end" className="diagram-small">
        PFD-001
      </text>
      {layout.routes.map(({ edge, path, recycle }) => {
        return (
          <g key={edge.id}>
            <path
              d={path}
              className={`flow-path${recycle ? ' recycle-path' : ''}`}
              markerEnd={edge.flowDirection === 'undirected' ? undefined : 'url(#flow-arrow)'}
            />
          </g>
        );
      })}
      {layout.nodes.map(node => (
        <g
          key={node.id}
          className={`diagram-node ${selected === node.id ? 'is-selected' : ''}`}
          role="button"
          aria-label={`Select ${node.id}`}
          tabIndex={0}
          onClick={() => onSelect(node.id)}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSelect(node.id);
            }
          }}
          onMouseEnter={() => onHover(node.id)}
          onMouseLeave={() => onHover(null)}
        >
          <rect
            x={node.x - (node.kind === 'junction' ? 14 : 37)}
            y={node.y - (node.kind === 'junction' ? 14 : 44)}
            width={node.kind === 'junction' ? 28 : 74}
            height={node.kind === 'junction' ? 28 : 88}
            rx="7"
            className="node-hit"
          />
          {node.dutyStandby ? (
            <g transform={`translate(${node.x},${node.y})`}>
              <g transform="translate(-20,0) scale(.65)">
                <EquipmentSymbol kind="pump" />
              </g>
              <g transform="translate(20,0) scale(.65)">
                <EquipmentSymbol kind="pump" />
              </g>
            </g>
          ) : (
            <EquipmentSymbol kind={node.kind} x={node.x} y={node.y} />
          )}
          <text x={node.x} y={node.y - 58} textAnchor="middle" className="diagram-node-label">
            {node.dutyStandby ? `${node.id}A / ${node.id}B` : node.id}
          </text>
          {node.kind !== 'junction' && (
            <>
              <text x={node.x} y={node.y + 44} textAnchor="middle" className="diagram-node-name">
                {node.name}
              </text>
              <rect x={node.x - 60} y={node.y + 59} width="120" height="23" rx="4" className="metadata-bg" />
              <text x={node.x} y={node.y + 74} textAnchor="middle" className="metadata-text">
                {node.tags}
              </text>
              <circle cx={node.x + 32} cy={node.y - 41} r="3" className="verified-dot" />
            </>
          )}
          {topology && (
            <>
              <title>{node.sourceBounds ? `PDF page ${node.sourcePage ?? 0} coordinates ${node.sourceBounds.join(', ')}` : node.label}</title>
            </>
          )}
        </g>
      ))}
      {!topology && (
        <>
          <text x="25" y={layout.height - 24} className="diagram-small">
            {equipmentCount} EQUIPMENT ITEMS
          </text>
          <text x={layout.width - 25} y={layout.height - 24} textAnchor="end" className="diagram-small">
            {edges.some(edge => edge.flowDirection === 'undirected')
              ? 'FLOW DIRECTION UNRESOLVED'
              : 'FLOW DIRECTION →'}
          </text>
        </>
      )}
      </svg>
    </div>
  );
}

function Valve({ x, y, vertical = false }: { x: number; y: number; vertical?: boolean }) {
  return (
    <g transform={`translate(${x},${y})${vertical ? ' rotate(90)' : ''}`}>
      <path d="M-8-6L8 6V-6L-8 6Z" />
      <path d="M0 0v-13h7" />
    </g>
  );
}
function Instrument({ x, y, label }: { x: number; y: number; label: string }) {
  return (
    <g>
      <circle cx={x} cy={y} r="13" />
      <path d={`M${x - 12} ${y}h24`} />
      <text x={x} y={y - 3} textAnchor="middle">
        {label.split('-')[0]}
      </text>
      <text x={x} y={y + 8} textAnchor="middle">
        {label.split('-')[1]}
      </text>
    </g>
  );
}

export function SourceDiagram({
  selected,
  onSelect,
  onHover,
  boxes,
  zoom,
  locating = false,
}: DiagramProps & { boxes: boolean; zoom: number; locating?: boolean }) {
  const regions = [
    { id: 'TK-101' as const, x: 69, y: 104, w: 108, h: 153, label: 'TK-101', kind: 'equipment' },
    { id: 'P-101' as const, x: 229, y: 183, w: 122, h: 138, label: 'P-101A / B', kind: 'equipment' },
    { id: 'E-102' as const, x: 403, y: 187, w: 84, h: 89, label: 'E-102', kind: 'equipment' },
    { id: 'V-102' as const, x: 504, y: 126, w: 61, h: 151, label: 'V-102', kind: 'equipment' },
    { id: 'TK-101' as const, x: 173, y: 80, w: 41, h: 40, label: 'PT-101', kind: 'tag' },
    { id: 'E-102' as const, x: 386, y: 124, w: 42, h: 43, label: 'FT-202', kind: 'tag' },
  ];
  return (
    <svg
      viewBox="0 0 600 390"
      className={`source-svg ${locating ? 'locating' : ''}`}
      role="img"
      aria-label="Original source P and ID drawing"
      onClick={e => {
        if (locating) {
          e.stopPropagation();
          onSelect('V-102');
        }
      }}
    >
      <defs>
        <pattern id="source-grid" width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M16 0H0V16" className="blueprint-grid" fill="none" />
        </pattern>
      </defs>
      <rect width="600" height="390" className="source-bg" />
      <rect width="600" height="390" fill="url(#source-grid)" />
      <g transform={`translate(300 195) scale(${zoom / 100}) translate(-300 -195)`}>
        <g className="blueprint-lines" fill="none" strokeWidth="1">
          <rect x="23" y="23" width="554" height="343" strokeWidth=".5" />
          <path d="M24 51H577 M46 24V366 M553 24V366 M24 338H577" strokeWidth=".4" />
          <path
            d="M47 164H90 M123 120V73H278V171 M123 238V260H232 M278 211H354V227H418 M318 288H354V227 M472 227H532V257 M532 143V73H447V151 M354 227V102H407V151 M123 73V58 M447 73H542"
            strokeWidth="1.6"
          />
          <path d="M61 307H514V271 M170 307V260 M201 307V260 M383 227V307 M447 260V307" />
          <path d="M195 104V135H123 M407 146V181H447 M278 153H240V204 M532 110H500V173" strokeDasharray="4 3" />
          <EquipmentSymbol kind="tank" x={123} y={180} />
          <path d="M100 153V127 Q123 113 146 127V153 M100 205V231Q123 245 146 231V205" />
          <EquipmentSymbol kind="pump" x={278} y={211} />
          <EquipmentSymbol kind="pump" x={278} y={288} />
          <path d="M232 260V211H256 M232 260V288H256 M300 211H318 M300 288H318 M318 211V288" />
          <EquipmentSymbol kind="exchanger" x={447} y={227} />
          <EquipmentSymbol kind="vessel" x={532} y={206} />
          <Valve x={188} y={260} />
          <Valve x={232} y={239} vertical />
          <Valve x={318} y={245} vertical />
          <Valve x={379} y={227} />
          <Valve x={499} y={227} />
          <Valve x={447} y={101} vertical />
          <Valve x={94} y={307} />
          <Valve x={354} y={151} vertical />
          <Instrument x={195} y={102} label="PT-101" />
          <Instrument x={407} y={146} label="FT-202" />
          <Instrument x={240} y={153} label="PI-101" />
          <Instrument x={500} y={110} label="LT-102" />
          <Instrument x={168} y={205} label="LI-101" />
          <Instrument x={379} y={185} label="TT-102" />
          <path d="M168 218v23h-22 M379 198v29 M278 188v-16 M278 265v-15" />
          <path d="M69 164l-6-3v6Z M211 260l-6-3v6Z M396 227l-6-3v6Z M526 73l-6-3v6Z" />
          <rect x="410" y="340" width="143" height="25" />
          <path d="M410 353H553 M470 340V365 M516 340V365" />
        </g>
        <g className="blueprint-text">
          <text x="59" y="42" className="drawing-title">
            PROCESS & INSTRUMENTATION DIAGRAM
          </text>
          <text x="532" y="42" textAnchor="end">
            UNIT 01 / REV. C
          </text>
          <text x="123" y="254" textAnchor="middle">
            TK-101
          </text>
          <text x="123" y="271" textAnchor="middle">
            FEED STORAGE
          </text>
          <text x="278" y="248" textAnchor="middle">
            P-101A
          </text>
          <text x="278" y="329" textAnchor="middle">
            P-101B
          </text>
          <text x="447" y="275" textAnchor="middle">
            E-102
          </text>
          <text x="532" y="264" textAnchor="middle">
            V-102
          </text>
          <text x="77" y="157">
            FEED IN
          </text>
          <text x="157" y="67">
            2”-P-101-CS150
          </text>
          <text x="366" y="94">
            1”-IA-202
          </text>
          <text x="361" y="220">
            2”-P-103-CS150
          </text>
          <text x="479" y="300">
            PRODUCT OUT
          </text>
          <text x="57" y="321">
            DRAIN HEADER
          </text>
          <text x="418" y="350">
            PROJECT ALPHA
          </text>
          <text x="476" y="350">
            P&amp;ID-001
          </text>
          <text x="524" y="350">
            REV C
          </text>
          <text x="418" y="362">
            SHEET 01 / 01
          </text>
          <text x="476" y="362">
            1:100
          </text>
          <text x="524" y="362">
            A1
          </text>
          <text x="34" y="100" transform="rotate(-90 34 100)">
            A
          </text>
          <text x="34" y="190" transform="rotate(-90 34 190)">
            B
          </text>
          <text x="34" y="285" transform="rotate(-90 34 285)">
            C
          </text>
        </g>
        {regions.map(region => (
          <g
            key={region.label}
            className={`bounding-region ${region.kind === 'tag' ? 'tag-region' : ''} ${selected === region.id ? 'is-selected' : ''} ${boxes || selected === region.id ? '' : 'boxes-hidden'}`}
            role="button"
            tabIndex={0}
            aria-label={`Source ${region.label}`}
            onClick={e => {
              e.stopPropagation();
              onSelect(region.id);
            }}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(region.id);
              }
            }}
            onMouseEnter={() => onHover(region.id)}
            onMouseLeave={() => onHover(null)}
          >
            <rect x={region.x} y={region.y} width={region.w} height={region.h} rx="2" />
            <path
              d={`M${region.x} ${region.y + 8}v-8h8 M${region.x + region.w - 8} ${region.y}h8v8 M${region.x} ${region.y + region.h - 8}v8h8 M${region.x + region.w - 8} ${region.y + region.h}h8v-8`}
              className="box-corners"
            />
            <rect x={region.x} y={region.y - 15} width={region.label.length * 5.5 + 12} height="15" className="box-label-bg" />
            <text x={region.x + 6} y={region.y - 5} className="box-label">
              {region.label}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}

export function IntersectionCrop({ resolution }: { resolution: string }) {
  const isJunction = /junction|connect|tee/i.test(resolution) && !/non-connecting|crossover|bridge/i.test(resolution);
  return (
    <svg viewBox="0 0 500 165" className="intersection-crop" role="img" aria-label="Enlarged pipe intersection with highlighted lines">
      <defs>
        <pattern id="crop-grid" width="18" height="18" patternUnits="userSpaceOnUse">
          <path d="M18 0H0V18" className="blueprint-grid" fill="none" />
        </pattern>
      </defs>
      <rect width="500" height="165" className="source-bg" />
      <rect width="500" height="165" fill="url(#crop-grid)" />
      <g className="blueprint-lines" fill="none">
        <path d="M0 40h100v90h400 M350 0v165 M70 0v165" />
        <circle cx="420" cy="130" r="22" />
        <path d="M410 117l23 13-23 13Z" />
      </g>
      <path d="M35 82H232" className="flow-path" />
      <path d={isJunction ? 'M232 82H467' : 'M232 82Q250 42 268 82H467'} className="flow-path" />
      <path d="M250 20V145" className="crossing-line" />
      {isJunction && <circle cx="250" cy="82" r="5" className="arrow-fill" />}
      <circle cx="250" cy="82" r="37" className="review-ring" />
      <text x="30" y="24" className="diagram-small">
        SOURCE CROP · 400%
      </text>
      <text x="368" y="151" className="diagram-small">
        P-101A
      </text>
    </svg>
  );
}
