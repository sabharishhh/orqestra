import { useEffect, useState } from 'react';
import ReactFlow, { Background, Controls, MarkerType, Handle, Position } from 'reactflow';
import 'reactflow/dist/style.css';
import { GitMerge, AlertCircle, Sparkles } from 'lucide-react';
import { fetchLineageGraph } from '../api';

const AgentNode = ({ data }) => (
  <div
    className="bg-[var(--color-surface-2)] border border-[var(--color-border-accent)] px-4 py-2.5 min-w-[160px] flex flex-col items-center"
    style={{ boxShadow: '0 0 0 1px var(--color-border-accent) inset' }}
  >
    <Handle type="target" position={Position.Top} className="opacity-0" />
    <span className="font-mono text-[10px] tracking-[0.05em] font-bold text-[var(--color-accent)] mb-0.5">
      AGENT
    </span>
    <span className="text-[14px] font-medium text-[var(--color-text-primary)]">
      {data.agentName || 'Unknown'}
    </span>
    <Handle type="source" position={Position.Bottom} className="opacity-0" />
  </div>
);

const ClaimNode = ({ data }) => {
  const isLCA = data.isLCA;
  const isConflict = data.isConflict;
  const depth = data.depth ?? 0;

  let borderColor = 'var(--color-border-default)';
  let borderWidth = '1px';
  let label = 'CLAIM';
  let labelColor = 'var(--color-text-tertiary)';

  if (isLCA) {
    borderColor = 'var(--color-accent)';
    borderWidth = '1.5px';
    label = 'LCA';
    labelColor = 'var(--color-accent)';
  } else if (isConflict) {
    borderColor = 'var(--color-sev-critical)';
    borderWidth = '1.5px';
    label = 'ROOT';
    labelColor = 'var(--color-sev-critical)';
  }

  return (
    <div
      className="bg-[var(--color-surface-1)] p-3 w-[280px]"
      style={{
        border: `${borderWidth} solid ${borderColor}`,
        opacity: depth > 0 && !isLCA && !isConflict ? 0.85 : 1,
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />

      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-1.5">
          <span
            className="font-mono text-[10px] tracking-[0.05em] font-bold"
            style={{ color: labelColor }}
          >
            {label}
          </span>
          {isLCA && <Sparkles size={11} strokeWidth={1.5} className="text-[var(--color-accent)]" />}
          {isConflict && <AlertCircle size={11} strokeWidth={1.5} className="text-[var(--color-sev-critical)]" />}
        </div>
        <span className="font-mono text-[10px] text-[var(--color-text-tertiary)] uppercase tracking-[0.02em]">
          {data.entityHint
            ? (data.entityHint.length > 20 ? data.entityHint.slice(0, 20) + '…' : data.entityHint)
            : 'unknown'}
        </span>
      </div>

      <div className="text-[12px] text-[var(--color-text-body)] leading-[16px] mb-2.5 line-clamp-3">
        {data.claimText}
      </div>

      <div className="flex justify-between items-center font-mono text-[10px]">
        <span className="text-[var(--color-text-secondary)]">
          {data.systemName || '—'}
        </span>
        <span className="text-[var(--color-text-tertiary)]">
          depth:{' '}
          <span style={{ color: depth === 0 ? 'var(--color-sev-critical)' : 'var(--color-text-secondary)' }}>
            {depth}
          </span>
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
};

const nodeTypes = { agentNode: AgentNode, claimNode: ClaimNode };

export default function ContradictionLineageTree({ conflict }) {
  const [graph, setGraph] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!conflict) return;
    setGraph(null);
    setError(null);
    fetchLineageGraph(conflict.id)
      .then(setGraph)
      .catch(() => setError('Unable to load lineage graph.'));
  }, [conflict?.id]);

  if (error) {
    return (
      <div className="h-[500px] bg-[var(--color-surface-0)] border border-[var(--color-border-default)] flex items-center justify-center">
        <div className="flex flex-col items-center text-center">
          <AlertCircle size={20} strokeWidth={1.5} className="text-[var(--color-text-disabled)] mb-3" />
          <div className="text-[13px] text-[var(--color-text-secondary)]">{error}</div>
        </div>
      </div>
    );
  }

  if (!graph) {
    return (
      <div className="h-[500px] bg-[var(--color-surface-0)] border border-[var(--color-border-default)] flex items-center justify-center">
        <div className="font-mono text-[12px] text-[var(--color-text-secondary)] animate-pulse">
          Computing causal lineage…
        </div>
      </div>
    );
  }

  const edgesWithMarkers = (graph.edges || []).map(e => ({
    ...e,
    style: { ...(e.style || {}), stroke: e.style?.stroke || 'var(--color-border-strong)' },
    markerEnd: e.markerEnd
      ? { type: MarkerType.ArrowClosed, color: e.style?.stroke || '#3F3F46' }
      : undefined,
  }));

  return (
    <div className="h-[560px] bg-[var(--color-surface-0)] border border-[var(--color-border-default)] relative overflow-hidden">
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 z-10 h-12 px-4 flex items-center justify-between border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
        <div className="flex items-center gap-2">
          <GitMerge size={16} strokeWidth={1.5} className="text-[var(--color-accent)]" />
          <span className="text-[13px] font-medium text-[var(--color-text-primary)]">
            Causal Lineage
          </span>
          <span className="font-mono text-[11px] text-[var(--color-text-tertiary)] ml-2">
            {graph.node_count} nodes · {graph.edge_count} edges
          </span>
        </div>

        {graph.has_shared_ancestor ? (
          <span
            className="inline-flex items-center gap-1.5 font-mono text-[11px] px-2 py-0.5 border"
            style={{
              color: 'var(--color-accent)',
              borderColor: 'var(--color-accent)',
              backgroundColor: 'color-mix(in srgb, var(--color-accent) 15%, transparent)',
            }}
          >
            <Sparkles size={11} strokeWidth={1.5} />
            LCA · fork A:{graph.fork_distance_a} / B:{graph.fork_distance_b}
          </span>
        ) : (
          <span
            className="inline-flex items-center font-mono text-[11px] px-2 py-0.5 border"
            style={{
              color: 'var(--color-sev-medium)',
              borderColor: 'var(--color-sev-medium)',
              backgroundColor: 'color-mix(in srgb, var(--color-sev-medium) 15%, transparent)',
            }}
          >
            No shared ancestor
          </span>
        )}
      </div>

      <div className="pt-12 h-full">
        <ReactFlow
          nodes={graph.nodes}
          edges={edgesWithMarkers}
          nodeTypes={nodeTypes}
          defaultViewport={{ x: 0, y: 0, zoom: 0.6 }}
          onInit={(instance) => {
            setTimeout(() => instance.fitView({ padding: 0.25, duration: 0 }), 50);
          }}
          minZoom={0.2}
          maxZoom={2}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          panOnDrag
          zoomOnScroll
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1A1A1A" gap={24} size={1} />
          <Controls
            showInteractive={false}
            className="!bg-[var(--color-surface-1)] !border !border-[var(--color-border-default)] [&>button]:!bg-[var(--color-surface-1)] [&>button]:!border-[var(--color-border-default)] [&>button]:!text-[var(--color-text-body)] [&>button:hover]:!bg-[var(--color-surface-2)]"
          />
        </ReactFlow>
      </div>
    </div>
  );
}