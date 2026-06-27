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
    <Handle type="target" position={Position.Top} className="!opacity-0 !w-1 !h-1 !border-0 !bg-transparent" />
    <Handle type="source" position={Position.Bottom} className="!opacity-0 !w-1 !h-1 !border-0 !bg-transparent" />
  </>
);

const SystemNode = ({ data }) => (
  <div
    className="bg-[var(--color-surface-2)] border-2 border-[var(--color-accent)] px-6 py-4 min-w-[180px] flex flex-col items-center"
    style={{ boxShadow: '0 0 24px -8px var(--color-accent)' }}
  >
    <UniversalHandles />
    <div className="font-mono text-[10px] font-bold tracking-[0.1em] text-[var(--color-accent)] mb-1">
      AGENT
    </div>
    <div className="text-[16px] font-bold text-[var(--color-text-primary)]">
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
    .force('link', forceLink(simEdges).id(d => d.id)
      .distance(link => {
        if (link.type === 'contradiction') return 220;
        if (link.type === 'about') return 90;
        return 55;
      })
      .strength(link => {
        if (link.type === 'contradiction') return 0.3;
        return 1.0;
      })
    )
    .force('charge', forceManyBody().strength(node => {
      if (node.type === 'system') return -6000;
      if (node.type === 'entity') return -2000;
      return -400;
    }).distanceMax(1200))
    .force('center', forceCenter(0, 0).strength(0.015))
    .force('collide', forceCollide().radius(node => {
      if (node.type === 'system') return 180;
      if (node.type === 'entity') return 100;
      return 110;
    }).strength(1))
    .force('x', forceX(0).strength(0.015))
    .force('y', forceY(0).strength(0.015));

  for (let i = 0; i < 600; i++) simulation.tick();

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
          type: 'default',
          animated,
          style: { strokeWidth, stroke: color },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
        };
      });

      const { layoutedNodes, layoutedEdges } = applyForceLayout(initialNodes, initialEdges);
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);

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

  const onNodeDrag = useCallback((event, draggedNode) => {
    if (draggedNode.type !== 'system') return;

    const connectedClaimIds = new Set();
    edges.forEach(e => {
      if (e.source === draggedNode.id) connectedClaimIds.add(e.target);
      if (e.target === draggedNode.id) connectedClaimIds.add(e.source);
    });

    const prev = nodes.find(n => n.id === draggedNode.id);
    if (!prev) return;
    const dx = draggedNode.position.x - prev.position.x;
    const dy = draggedNode.position.y - prev.position.y;
    if (dx === 0 && dy === 0) return;

    setNodes(curr => curr.map(n => {
      if (n.id === draggedNode.id) return n;
      if (!connectedClaimIds.has(n.id)) return n;
      if (n.type !== 'claim') return n;
      return { ...n, position: { x: n.position.x + dx, y: n.position.y + dy } };
    }));
  }, [nodes, edges, setNodes]);

  return (
    <div className="flex flex-col h-screen">
      <header className="h-14 px-6 flex items-center justify-between border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
        <div className="flex items-center gap-2">
          <Share2 size={16} strokeWidth={1.5} className="text-[var(--color-accent)]" />
          <h1 className="text-[18px] font-semibold text-[var(--color-text-primary)] tracking-[-0.01em]">
            Topology Graph
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
          onNodeDrag={onNodeDrag}
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