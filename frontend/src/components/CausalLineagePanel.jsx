import { useEffect, useState, useMemo } from 'react';
import { X, GitBranch, Sparkles, AlertCircle, ChevronDown } from 'lucide-react';
import { fetchLineageGraph } from '../api';

// =====================================================
// Layout constants — tuned for a 480px-wide slide-over panel
// =====================================================
const PANEL_PADDING_X = 32;
const RAIL_GAP = 140;                // horizontal distance between the two rails
const NODE_VERTICAL_GAP = 44;        // distance between ancestor nodes on a rail
const ROOT_CARD_HEIGHT = 96;
const ROOT_CARD_WIDTH = 180;
const LCA_NODE_HEIGHT = 56;
const CONTRADICTION_GAP = 32;        // vertical gap reserved for the CONTRADICTION line
const TOP_PADDING = 48;
const BOTTOM_PADDING = 24;

const RAIL_A_COLOR = 'var(--color-accent)';
const RAIL_B_COLOR = 'var(--color-sev-medium)';

// =====================================================
// Helpers — partition the graph nodes into two ancestor chains
// =====================================================
function partitionLineage(graph) {
  if (!graph || !graph.nodes) return { lca: null, sideA: [], sideB: [], rootA: null, rootB: null };

  const claimNodes = graph.nodes.filter(n => n.type === 'claimNode');
  const sideA = claimNodes.filter(n => n.data?.side === 'A' && n.data?.depth < 0).sort((a, b) => a.data.depth - b.data.depth);
  const sideB = claimNodes.filter(n => n.data?.side === 'B' && n.data?.depth < 0).sort((a, b) => a.data.depth - b.data.depth);
  const rootA = claimNodes.find(n => n.data?.side === 'A' && n.data?.depth === 0);
  const rootB = claimNodes.find(n => n.data?.side === 'B' && n.data?.depth === 0);
  const lca = claimNodes.find(n => n.data?.isLCA === true);

  return { lca, sideA, sideB, rootA, rootB };
}

// =====================================================
// Tooltip — appears on hover, follows the node
// =====================================================
function NodeTooltip({ node, x, y, side }) {
  if (!node) return null;
  const claim = node.data?.claimText || node.data?.claim_text || '';
  return (
    <div
      className="fixed z-[60] pointer-events-none"
      style={{ left: x + 14, top: y - 8, maxWidth: '320px' }}
    >
      <div
        className="px-3 py-2 text-[12px] font-mono leading-[18px] border bg-[var(--color-surface-0)]"
        style={{
          color: 'var(--color-text-body)',
          borderColor: side === 'A' ? RAIL_A_COLOR : RAIL_B_COLOR,
        }}
      >
        <div className="text-[10px] font-bold uppercase tracking-[0.05em] mb-1" style={{ color: side === 'A' ? RAIL_A_COLOR : RAIL_B_COLOR }}>
          {node.data?.entityHint || '—'} · depth {node.data?.depth}
        </div>
        <div className="text-[12px]">{claim || '(no claim text)'}</div>
        {node.data?.systemName && (
          <div className="text-[10px] text-[var(--color-text-tertiary)] mt-1.5">
            {node.data.systemName}
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================
// Ancestor rail node — small circle with click-to-pin
// =====================================================
function RailNode({ node, side, isPinned, onPin, onHover, onUnhover }) {
  const color = side === 'A' ? RAIL_A_COLOR : RAIL_B_COLOR;
  return (
    <g
      className="cursor-pointer"
      onClick={(e) => { e.stopPropagation(); onPin?.(node); }}
      onMouseEnter={(e) => onHover?.(node, e)}
      onMouseLeave={() => onUnhover?.()}
    >
      <circle r={isPinned ? 9 : 6} fill={color} opacity={isPinned ? 1 : 0.85} />
      <circle r={isPinned ? 14 : 10} fill="none" stroke={color} strokeWidth={isPinned ? 2 : 0} opacity={0.5} />
    </g>
  );
}

// =====================================================
// Pinned card — expanded inline detail when a node is clicked
// =====================================================
function PinnedCard({ node, side, onClose }) {
  if (!node) return null;
  const color = side === 'A' ? RAIL_A_COLOR : RAIL_B_COLOR;
  return (
    <div
      className="mt-2 mx-2 p-3 border bg-[var(--color-surface-2)]"
      style={{ borderColor: color }}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <div className="text-[10px] font-bold uppercase tracking-[0.05em]" style={{ color }}>
          {node.data?.entityHint || '—'} · depth {node.data?.depth}
        </div>
        <button
          onClick={onClose}
          className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] -mt-1"
        >
          <X size={12} strokeWidth={1.5} />
        </button>
      </div>
      <div className="text-[12px] font-mono text-[var(--color-text-body)] leading-[18px]">
        {node.data?.claimText || '(no claim text)'}
      </div>
      {node.data?.systemName && (
        <div className="text-[10px] text-[var(--color-text-tertiary)] mt-2 font-mono">
          {node.data.systemName}
        </div>
      )}
    </div>
  );
}

// =====================================================
// SVG rendering of the two-rail diagram
// =====================================================
function LineageDiagram({ graph, onPin, pinnedIds, hoveredNode, setHoveredNode }) {
  const { lca, sideA, sideB, rootA, rootB } = useMemo(() => partitionLineage(graph), [graph]);

  // Build a vertical layout.
  // Total height = TOP_PADDING + LCA (if present) + max(sideA, sideB) * NODE_VERTICAL_GAP + ROOT cards + CONTRADICTION gap + BOTTOM_PADDING
  const ancestorCount = Math.max(sideA.length, sideB.length);
  const lcaSection = lca ? LCA_NODE_HEIGHT + 24 : 0;
  const ancestorSection = ancestorCount * NODE_VERTICAL_GAP;
  const rootSection = ROOT_CARD_HEIGHT + CONTRADICTION_GAP + ROOT_CARD_HEIGHT;
  const totalHeight = TOP_PADDING + lcaSection + ancestorSection + rootSection + BOTTOM_PADDING;

  // Horizontal centers
  const panelWidth = 480 - PANEL_PADDING_X * 2;  // 416
  const centerX = panelWidth / 2;
  const railAX = centerX - RAIL_GAP / 2;
  const railBX = centerX + RAIL_GAP / 2;

  // Vertical positions
  const lcaY = lca ? TOP_PADDING + LCA_NODE_HEIGHT / 2 : null;
  const ancestorsStartY = TOP_PADDING + lcaSection;
  const rootAY = ancestorsStartY + ancestorSection + ROOT_CARD_HEIGHT / 2;
  const rootBY = rootAY + ROOT_CARD_HEIGHT + CONTRADICTION_GAP;
  const contradictionY = (rootAY + ROOT_CARD_HEIGHT / 2 + rootBY - ROOT_CARD_HEIGHT / 2) / 2;

  // Animation: keyed off graph.contradiction_id so re-opens re-trigger
  const [animKey, setAnimKey] = useState(0);
  useEffect(() => { setAnimKey(k => k + 1); }, [graph?.contradiction_id]);

  return (
    <div className="relative" style={{ paddingLeft: PANEL_PADDING_X, paddingRight: PANEL_PADDING_X }}>
      {/* "past" label */}
      <div className="absolute top-2 left-0 right-0 text-center text-[10px] font-mono uppercase tracking-[0.1em] text-[var(--color-text-disabled)]">
        past
      </div>

      <svg
        width={panelWidth}
        height={totalHeight}
        key={animKey}
        className="overflow-visible"
        style={{ display: 'block' }}
      >
        <defs>
          <style>{`
            @keyframes drawDown {
              from { stroke-dashoffset: var(--len); }
              to   { stroke-dashoffset: 0; }
            }
            @keyframes fadeIn {
              from { opacity: 0; }
              to   { opacity: 1; }
            }
            @keyframes scaleIn {
              from { transform: scale(0.92); opacity: 0; }
              to   { transform: scale(1);    opacity: 1; }
            }
            .rail-line {
              stroke-dasharray: 1000;
              animation: drawDown 600ms ease-out forwards;
              --len: 1000;
            }
            .ancestor-node {
              animation: fadeIn 400ms ease-out 400ms forwards;
              opacity: 0;
            }
            .lca-node-anim {
              animation: fadeIn 400ms ease-out 100ms forwards;
              opacity: 0;
            }
            .contradiction-line {
              stroke-dasharray: 6 4;
              animation: fadeIn 400ms ease-out 800ms forwards, dashflow 1.4s linear 800ms infinite;
              opacity: 0;
            }
            @keyframes dashflow {
              to { stroke-dashoffset: -20; }
            }
          `}</style>
        </defs>

        {/* LCA section: merged rail at top, then Y-fork down */}
        {lca && lcaY !== null && (
          <g>
            {/* The dotted upward line above the LCA representing 'shared past' */}
            <line
              x1={centerX} y1={4} x2={centerX} y2={lcaY - LCA_NODE_HEIGHT / 2}
              stroke="var(--color-border-strong)"
              strokeWidth={2}
              strokeDasharray="2 4"
              className="rail-line"
            />
            {/* LCA node — pill with sparkle */}
            <g
              transform={`translate(${centerX - 56}, ${lcaY - 18})`}
              className="lca-node-anim cursor-pointer"
              onClick={(e) => { e.stopPropagation(); onPin?.(lca); }}
              onMouseEnter={(e) => setHoveredNode({ node: lca, side: 'LCA', x: e.clientX, y: e.clientY })}
              onMouseLeave={() => setHoveredNode(null)}
            >
              <rect width={112} height={36} rx={0}
                fill="var(--color-surface-2)"
                stroke="var(--color-accent)"
                strokeWidth={1.5}
              />
              <text x={56} y={15} fill="var(--color-accent)" fontSize={10} fontFamily="JetBrains Mono, monospace" textAnchor="middle" fontWeight={700} letterSpacing={1}>
                SHARED ORIGIN
              </text>
              <text x={56} y={28} fill="var(--color-text-body)" fontSize={10} fontFamily="JetBrains Mono, monospace" textAnchor="middle">
                {(lca.data?.entityHint || '').slice(0, 18)}
              </text>
            </g>
            {/* Y-fork from LCA to two rails */}
            <path
              d={`M ${centerX} ${lcaY + LCA_NODE_HEIGHT / 2 - 4}
                  L ${centerX} ${ancestorsStartY - 12}
                  L ${railAX} ${ancestorsStartY}
                  M ${centerX} ${ancestorsStartY - 12}
                  L ${railBX} ${ancestorsStartY}`}
              stroke="var(--color-border-strong)"
              strokeWidth={2}
              fill="none"
              className="rail-line"
              style={{ animationDelay: '200ms' }}
            />
          </g>
        )}

        {/* If no LCA, label both rail tops as "independent origin" */}
        {!lca && (
          <text
            x={centerX} y={20}
            fill="var(--color-sev-medium)"
            fontSize={10}
            fontFamily="JetBrains Mono, monospace"
            textAnchor="middle"
            fontWeight={700}
            letterSpacing={1}
            className="lca-node-anim"
          >
            ⚠ INDEPENDENT ORIGINS
          </text>
        )}

        {/* Rail A — vertical line */}
        <line
          x1={railAX} y1={ancestorsStartY}
          x2={railAX} y2={rootAY - ROOT_CARD_HEIGHT / 2}
          stroke={RAIL_A_COLOR}
          strokeWidth={2}
          className="rail-line"
          style={{ animationDelay: lca ? '300ms' : '100ms' }}
        />

        {/* Rail B — vertical line */}
        <line
          x1={railBX} y1={ancestorsStartY}
          x2={railBX} y2={rootBY - ROOT_CARD_HEIGHT / 2}
          stroke={RAIL_B_COLOR}
          strokeWidth={2}
          className="rail-line"
          style={{ animationDelay: lca ? '300ms' : '100ms' }}
        />

        {/* Ancestor nodes — side A */}
        {sideA.map((n, i) => {
          const y = ancestorsStartY + (i + 0.5) * NODE_VERTICAL_GAP;
          const isPinned = pinnedIds.has(n.id);
          return (
            <g
              key={`a-${n.id}`}
              transform={`translate(${railAX}, ${y})`}
              className="ancestor-node"
              style={{ animationDelay: `${500 + i * 60}ms` }}
            >
              <RailNode
                node={n}
                side="A"
                isPinned={isPinned}
                onPin={onPin}
                onHover={(node, e) => setHoveredNode({ node, side: 'A', x: e.clientX, y: e.clientY })}
                onUnhover={() => setHoveredNode(null)}
              />
            </g>
          );
        })}

        {/* Ancestor nodes — side B */}
        {sideB.map((n, i) => {
          const y = ancestorsStartY + (i + 0.5) * NODE_VERTICAL_GAP;
          const isPinned = pinnedIds.has(n.id);
          return (
            <g
              key={`b-${n.id}`}
              transform={`translate(${railBX}, ${y})`}
              className="ancestor-node"
              style={{ animationDelay: `${500 + i * 60}ms` }}
            >
              <RailNode
                node={n}
                side="B"
                isPinned={isPinned}
                onPin={onPin}
                onHover={(node, e) => setHoveredNode({ node, side: 'B', x: e.clientX, y: e.clientY })}
                onUnhover={() => setHoveredNode(null)}
              />
            </g>
          );
        })}

        {/* ROOT A — big card */}
        {rootA && (
          <g
            transform={`translate(${railAX - ROOT_CARD_WIDTH / 2}, ${rootAY - ROOT_CARD_HEIGHT / 2})`}
            className="lca-node-anim cursor-pointer"
            style={{ animationDelay: '700ms', transformOrigin: 'center' }}
            onClick={(e) => { e.stopPropagation(); onPin?.(rootA); }}
            onMouseEnter={(e) => setHoveredNode({ node: rootA, side: 'A', x: e.clientX, y: e.clientY })}
            onMouseLeave={() => setHoveredNode(null)}
          >
            <rect width={ROOT_CARD_WIDTH} height={ROOT_CARD_HEIGHT}
              fill="var(--color-surface-2)"
              stroke="var(--color-sev-critical)"
              strokeWidth={2}
            />
            <text x={8} y={16} fill="var(--color-sev-critical)" fontSize={10} fontFamily="JetBrains Mono, monospace" fontWeight={700} letterSpacing={1}>
              ROOT · A
            </text>
            <text x={8} y={32} fill="var(--color-accent)" fontSize={10} fontFamily="JetBrains Mono, monospace">
              {(rootA.data?.systemName || '').slice(0, 22)}
            </text>
            <foreignObject x={6} y={38} width={ROOT_CARD_WIDTH - 12} height={ROOT_CARD_HEIGHT - 44}>
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  lineHeight: '14px',
                  color: 'var(--color-text-body)',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 4,
                  WebkitBoxOrient: 'vertical',
                }}
              >
                {rootA.data?.claimText || ''}
              </div>
            </foreignObject>
          </g>
        )}

        {/* ROOT B — big card */}
        {rootB && (
          <g
            transform={`translate(${railBX - ROOT_CARD_WIDTH / 2}, ${rootBY - ROOT_CARD_HEIGHT / 2})`}
            className="lca-node-anim cursor-pointer"
            style={{ animationDelay: '700ms', transformOrigin: 'center' }}
            onClick={(e) => { e.stopPropagation(); onPin?.(rootB); }}
            onMouseEnter={(e) => setHoveredNode({ node: rootB, side: 'B', x: e.clientX, y: e.clientY })}
            onMouseLeave={() => setHoveredNode(null)}
          >
            <rect width={ROOT_CARD_WIDTH} height={ROOT_CARD_HEIGHT}
              fill="var(--color-surface-2)"
              stroke="var(--color-sev-critical)"
              strokeWidth={2}
            />
            <text x={8} y={16} fill="var(--color-sev-critical)" fontSize={10} fontFamily="JetBrains Mono, monospace" fontWeight={700} letterSpacing={1}>
              ROOT · B
            </text>
            <text x={8} y={32} fill="var(--color-sev-medium)" fontSize={10} fontFamily="JetBrains Mono, monospace">
              {(rootB.data?.systemName || '').slice(0, 22)}
            </text>
            <foreignObject x={6} y={38} width={ROOT_CARD_WIDTH - 12} height={ROOT_CARD_HEIGHT - 44}>
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  lineHeight: '14px',
                  color: 'var(--color-text-body)',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 4,
                  WebkitBoxOrient: 'vertical',
                }}
              >
                {rootB.data?.claimText || ''}
              </div>
            </foreignObject>
          </g>
        )}

        {/* CONTRADICTION line between the two ROOTs */}
        {rootA && rootB && (
          <g className="contradiction-line">
            <line
              x1={railAX} y1={rootAY + ROOT_CARD_HEIGHT / 2}
              x2={railBX} y2={rootBY - ROOT_CARD_HEIGHT / 2}
              stroke="var(--color-sev-critical)"
              strokeWidth={2.5}
              fill="none"
            />
            <rect
              x={centerX - 50} y={contradictionY - 9}
              width={100} height={18}
              fill="var(--color-surface-1)"
              stroke="var(--color-sev-critical)"
              strokeWidth={1}
            />
            <text
              x={centerX} y={contradictionY + 4}
              fill="var(--color-sev-critical)"
              fontSize={10}
              fontFamily="JetBrains Mono, monospace"
              fontWeight={700}
              letterSpacing={1}
              textAnchor="middle"
            >
              CONTRADICTION
            </text>
          </g>
        )}
      </svg>

      {/* "now" label */}
      <div
        className="absolute left-0 right-0 text-center text-[10px] font-mono uppercase tracking-[0.1em] text-[var(--color-text-disabled)]"
        style={{ top: totalHeight + 8 }}
      >
        now
      </div>
    </div>
  );
}

// =====================================================
// Main slide-over panel
// =====================================================
export default function CausalLineagePanel({ contradiction, onClose }) {
  const [graph, setGraph] = useState(null);
  const [error, setError] = useState(null);
  const [pinnedIds, setPinnedIds] = useState(new Set());
  const [hoveredNode, setHoveredNode] = useState(null);

  // ESC closes
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Fetch lineage when contradiction changes
  useEffect(() => {
    if (!contradiction?.id) {
      setGraph(null);
      return;
    }
    setGraph(null);
    setError(null);
    setPinnedIds(new Set());

    fetchLineageGraph(contradiction.id)
      .then(setGraph)
      .catch((err) => {
        console.warn('Lineage graph fetch failed:', err);
        setError('Unable to load lineage data.');
      });
  }, [contradiction?.id]);

  const handlePin = (node) => {
    if (!node) return;
    setPinnedIds(prev => {
      const next = new Set(prev);
      if (next.has(node.id)) {
        next.delete(node.id);
      } else {
        next.add(node.id);
      }
      return next;
    });
  };

  const isOpen = !!contradiction;
  const idShort = graph?.contradiction_id?.slice(0, 8).toUpperCase();

  // Derive pinned nodes from pinnedIds at render time.
  // Single source of truth → no possible drift, no StrictMode double-append.
  const pinnedNodesDerived = graph?.nodes
    ? graph.nodes.filter(n => n.type === 'claimNode' && pinnedIds.has(n.id))
    : [];

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={`fixed inset-0 bg-black/40 backdrop-blur-[2px] z-40 transition-opacity duration-200 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
      />

      {/* Panel */}
      <aside
        className={`fixed top-0 right-0 h-screen w-[480px] bg-[var(--color-surface-1)] border-l border-[var(--color-border-default)] z-50 flex flex-col transition-transform duration-200 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-[var(--color-border-default)] bg-[var(--color-surface-2)] shrink-0">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <GitBranch size={16} strokeWidth={1.5} style={{ color: 'var(--color-accent)' }} className="shrink-0" />
              <h2 className="text-[15px] font-semibold text-[var(--color-text-primary)] truncate">
                Causal Lineage
              </h2>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {idShort && (
                <span className="text-[11px] font-mono text-[var(--color-text-tertiary)] bg-[var(--color-surface-0)] border border-[var(--color-border-default)] px-2 py-1">
                  #{idShort}
                </span>
              )}
              <button
                onClick={onClose}
                className="p-1 hover:bg-[var(--color-surface-3)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
                aria-label="Close panel"
              >
                <X size={16} strokeWidth={1.5} />
              </button>
            </div>
          </div>
          {graph && (
            <div className="mt-2 flex items-center justify-between gap-2 text-[11px] font-mono">
              <div className="text-[var(--color-text-tertiary)]">
                {(graph.nodes?.filter(n => n.type === 'claimNode' && n.data?.depth < 0).length) || 0} ancestors
              </div>
              {graph.has_shared_ancestor ? (
                <span
                  className="inline-flex items-center gap-1 px-2 py-0.5 border"
                  style={{
                    color: 'var(--color-accent)',
                    borderColor: 'var(--color-accent)',
                    backgroundColor: 'color-mix(in srgb, var(--color-accent) 12%, transparent)',
                  }}
                >
                  <Sparkles size={11} strokeWidth={1.5} />
                  shared origin · fork A:{graph.fork_distance_a} / B:{graph.fork_distance_b}
                </span>
              ) : (
                <span
                  className="inline-flex items-center gap-1 px-2 py-0.5 border"
                  style={{
                    color: 'var(--color-sev-medium)',
                    borderColor: 'var(--color-sev-medium)',
                    backgroundColor: 'color-mix(in srgb, var(--color-sev-medium) 12%, transparent)',
                  }}
                >
                  <AlertCircle size={11} strokeWidth={1.5} />
                  independent origins
                </span>
              )}
            </div>
          )}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {!graph && !error && (
            <div className="h-full flex items-center justify-center text-[var(--color-text-tertiary)] text-[12px] font-mono animate-pulse">
              Computing causal lineage…
            </div>
          )}

          {error && (
            <div className="h-full flex flex-col items-center justify-center text-[var(--color-text-tertiary)] text-[12px] font-mono p-8 text-center">
              <AlertCircle size={20} strokeWidth={1.5} className="mb-2 opacity-40" />
              {error}
            </div>
          )}

          {graph && (
            <>
              <LineageDiagram
                graph={graph}
                onPin={handlePin}
                pinnedIds={pinnedIds}
                hoveredNode={hoveredNode}
                setHoveredNode={setHoveredNode}
              />

              {/* Pinned cards section — derived from pinnedIds, immune to StrictMode double-append */}
              {pinnedNodesDerived.length > 0 && (
                <div className="mt-6 pt-4 border-t border-[var(--color-border-default)]">
                  <div className="px-5 mb-2 flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-[0.05em] text-[var(--color-text-tertiary)]">
                      Pinned claims
                    </span>
                    <button
                      onClick={() => setPinnedIds(new Set())}
                      className="text-[10px] font-mono text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
                    >
                      clear all
                    </button>
                  </div>
                  <div className="pb-4">
                    {pinnedNodesDerived.map(n => (
                      <PinnedCard
                        key={n.id}
                        node={n}
                        side={n.data?.side || 'A'}
                        onClose={() => handlePin(n)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer hint */}
        <div className="px-5 py-3 border-t border-[var(--color-border-default)] bg-[var(--color-surface-2)] shrink-0">
          <div className="text-[10px] font-mono text-[var(--color-text-tertiary)] text-center">
            hover for preview · click to pin · esc to close
          </div>
        </div>
      </aside>

      {/* Floating hover tooltip */}
      {hoveredNode && (
        <NodeTooltip
          node={hoveredNode.node}
          side={hoveredNode.side}
          x={hoveredNode.x}
          y={hoveredNode.y}
        />
      )}
    </>
  );
}