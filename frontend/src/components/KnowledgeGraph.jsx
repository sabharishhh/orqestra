import { useEffect, useCallback, useRef } from 'react';
import ReactFlow, {
  Background, Controls, MarkerType,
  useNodesState, useEdgesState, Handle, Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide, forceX, forceY } from 'd3-force';
import { Database, Share2 } from 'lucide-react';


const UniversalHandles = () => (
  <>
    <Handle type="target" position={Position.Top} className="opacity-0" />
    <Handle type="source" position={Position.Bottom} className="opacity-0" />
    <Handle type="target" position={Position.Left} className="opacity-0" />
    <Handle type="source" position={Position.Right} className="opacity-0" />
  </>
);

const SystemNode = ({ data }) => (
  <div
    className="bg-[var(--color-surface-1)] border-[1.5px] border-[var(--color-accent)] px-4 py-3 min-w-[140px] flex flex-col items-center"
  >
    <UniversalHandles />
    <div className="font-mono text-[10px] font-bold tracking-[0.05em] text-[var(--color-accent)] mb-0.5">
      AGENT
    </div>
    <div className="text-[14px] font-semibold text-[var(--color-text-primary)]">
      {data.label}
    </div>
  </div>
);

const EntityNode = ({ data }) => (
  <div className="bg-[var(--color-surface-1)] border-[1.5px] border-[var(--color-ok)] px-4 py-3 min-w-[140px] flex flex-col items-center">
    <UniversalHandles />
    <Database size={14} strokeWidth={1.5} className="text-[var(--color-ok)] mb-1.5" />
    <div className="font-mono text-[10px] font-bold tracking-[0.05em] text-[var(--color-ok)] mb-0.5">
      ENTITY
    </div>
    <div className="text-[13px] font-medium text-[var(--color-text-primary)] text-center leading-tight">
      {data.label}
    </div>
  </div>
);

const ClaimNode = ({ data }) => (
  <div className="bg-[var(--color-surface-1)] border border-[var(--color-border-default)] p-3 min-w-[240px] max-w-[280px]">
    <UniversalHandles />
    <div className="flex justify-between items-center mb-2 pb-2 border-b border-[var(--color-border-default)]">
      <span className="font-mono text-[10px] font-bold tracking-[0.05em] text-[var(--color-text-tertiary)]">
        CLAIM
      </span>
      <span className="font-mono text-[10px] text-[var(--color-accent)] truncate max-w-[120px]">
        {data.topic}
      </span>
    </div>
    <div className="text-[12px] text-[var(--color-text-body)] leading-[16px]">
      {data.label}
    </div>
  </div>
);

const nodeTypes = { system: SystemNode, claim: ClaimNode, entity: EntityNode };

const applyForceLayout = (nodes, edges) => {
  const simNodes = nodes.map(n => ({ ...n, x: Math.random() * 400 - 200, y: Math.random() * 400 - 200 }));
  const simEdges = edges.map(e => ({ ...e }));

  const simulation = forceSimulation(simNodes)
    .force('link', forceLink(simEdges).id(d => d.id).distance(link => {
      if (link.type === 'contradiction') return 80;
      if (link.type === 'about') return 60;
      return 120;
    }).strength(0.6))
    .force('charge', forceManyBody().strength(-600).distanceMax(500))
    .force('center', forceCenter(0, 0).strength(0.08))
    .force('collide', forceCollide().radius(node => {
      if (node.type === 'system') return 80;
      if (node.type === 'entity') return 70;
      return 110;
    }).strength(0.9))
    .force('x', forceX(0).strength(0.04))
    .force('y', forceY(0).strength(0.04));

  for (let i = 0; i < 500; i++) simulation.tick();

  return {
    layoutedNodes: simNodes.map(n => ({ ...n, position: { x: n.x, y: n.y } })),
    layoutedEdges: edges,
  };
};

export default function KnowledgeGraph() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const graphSignatureRef = useRef('');
  const reactFlowInstance = useRef(null);

  const fetchGraphData = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/graph/');
      const data = await res.json();
      const sig = `${data.nodes.length}-${data.links.length}`;
      if (graphSignatureRef.current === sig) return;
      graphSignatureRef.current = sig;

      const initialNodes = data.nodes.map(n => {
        let label = n.name;
        let topic = '';
        if (n.group === 'claim') {
          const m = n.name.match(/^\[(.*?)\] (.*)$/);
          if (m) { topic = m[1]; label = m[2]; }
        }
        return { id: n.id, type: n.group, data: { label, topic }, position: { x: 0, y: 0 } };
      });

      const initialEdges = data.links.map(l => {
        let color, strokeWidth, animated;
        if (l.type === 'contradiction')      { color = '#F87171'; strokeWidth = 2;   animated = true; }
        else if (l.type === 'about')         { color = '#4ADE80'; strokeWidth = 1.5; animated = false; }
        else                                 { color = '#3F3F46'; strokeWidth = 1;   animated = false; }
        return {
          id: `${l.source}-${l.target}-${l.type}`,
          source: l.source, target: l.target,
          type: 'straight', animated,
          style: { strokeWidth, stroke: color },
          markerEnd: { type: MarkerType.ArrowClosed, color },
        };
      });

      const { layoutedNodes, layoutedEdges } = applyForceLayout(initialNodes, initialEdges);
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);

      // Refit view once layout settles
      setTimeout(() => {
        reactFlowInstance.current?.fitView({ padding: 0.2, duration: 400 });
      }, 50);

    } catch (e) {
      console.error('Failed to fetch graph data', e);
    }
  }, [setNodes, setEdges]);

  useEffect(() => {
    fetchGraphData();
    const t = setInterval(fetchGraphData, 10000);
    return () => clearInterval(t);
  }, [fetchGraphData]);

  return (
    <div className="flex flex-col h-screen">
      <header className="h-14 px-6 flex items-center justify-between border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
        <div className="flex items-center gap-2">
          <Share2 size={16} strokeWidth={1.5} className="text-[var(--color-accent)]" />
          <h1 className="text-[18px] font-semibold text-[var(--color-text-primary)] tracking-[-0.01em]">
            Knowledge Graph
          </h1>
        </div>
        <span className="font-mono text-[13px] text-[var(--color-text-secondary)]">
          {nodes.length} nodes · {edges.length} edges
        </span>
      </header>

      <div className="flex-1 relative bg-[var(--color-surface-0)]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onInit={(instance) => { reactFlowInstance.current = instance; }}
          defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1A1A1A" gap={24} size={1} />
          <Controls
            showInteractive={false}
            className="!bg-[var(--color-surface-1)] !border !border-[var(--color-border-default)] [&>button]:!bg-[var(--color-surface-1)] [&>button]:!border-[var(--color-border-default)] [&>button]:!text-[var(--color-text-body)] [&>button:hover]:!bg-[var(--color-surface-2)]"
          />
        </ReactFlow>

        {/* Legend */}
        <div className="absolute top-4 left-4 bg-[var(--color-surface-1)] border border-[var(--color-border-default)] px-4 py-3 pointer-events-none">
          <div className="text-[11px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-2">
            Legend
          </div>
          <div className="flex flex-col gap-1.5 font-mono text-[11px] text-[var(--color-text-secondary)]">
            <LegendItem color="var(--color-accent)" label="Agent" />
            <LegendItem color="var(--color-ok)" label="Entity" />
            <LegendItem color="var(--color-border-strong)" label="Claim" box />
            <LegendItem color="var(--color-sev-critical)" label="Contradiction" line />
          </div>
        </div>
      </div>
    </div>
  );
}

function LegendItem({ color, label, box, line }) {
  return (
    <span className="flex items-center gap-2">
      <span
        className="inline-block"
        style={
          line
            ? { width: 16, height: 2, background: color }
            : box
              ? { width: 10, height: 10, border: `1px solid ${color}` }
              : { width: 10, height: 10, background: color }
        }
      />
      {label}
    </span>
  );
}