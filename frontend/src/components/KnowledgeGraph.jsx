import { useEffect, useCallback, useRef } from 'react';
import ReactFlow, { 
    Background, 
    Controls, 
    MarkerType, 
    useNodesState, 
    useEdgesState,
    Handle,
    Position
} from 'reactflow';
import 'reactflow/dist/style.css';
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force';

// --- CUSTOM UI NODES (HTML Graph Cards) ---
const UniversalHandles = () => (
    <>
        <Handle type="target" position={Position.Top} className="opacity-0" />
        <Handle type="source" position={Position.Bottom} className="opacity-0" />
        <Handle type="target" position={Position.Left} className="opacity-0" />
        <Handle type="source" position={Position.Right} className="opacity-0" />
    </>
);

const SystemNode = ({ data }) => (
    <div className="px-6 py-4 shadow-[0_0_20px_rgba(59,130,246,0.3)] rounded-full bg-blue-950/80 border-2 border-blue-500 backdrop-blur-md text-center flex flex-col items-center justify-center min-w-[140px] min-h-[140px]">
        <UniversalHandles />
        <div className="text-[10px] font-bold uppercase tracking-widest text-blue-400 mb-1">Agent Core</div>
        <div className="text-lg font-bold text-white">{data.label}</div>
    </div>
);

const ClaimNode = ({ data }) => (
    <div className="p-4 shadow-xl rounded-xl bg-slate-900 border border-slate-700 min-w-[260px] max-w-[300px]">
        <UniversalHandles />
        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2 border-b border-slate-800 pb-2 flex justify-between items-center">
            <span>Extracted Claim</span>
            <span className="bg-slate-800 px-2 py-0.5 rounded text-blue-400">{data.topic}</span>
        </div>
        <div className="text-sm text-slate-300 leading-relaxed font-mono">
            "{data.label}"
        </div>
    </div>
);

const nodeTypes = { system: SystemNode, claim: ClaimNode };

// --- ORGANIC PHYSICS ENGINE ---
const applyForceLayout = (nodes, edges) => {
    // Clone elements for the simulation
    const simNodes = nodes.map(n => ({ ...n, x: Math.random() * 1000, y: Math.random() * 1000 }));
    const simEdges = edges.map(e => ({ ...e }));

    const simulation = forceSimulation(simNodes)
        // Contradictions pull together tightly (150), Ownership links orbit further out (250)
        .force('link', forceLink(simEdges).id(d => d.id).distance(link => link.animated ? 150 : 250))
        // High negative charge ensures HTML cards never overlap
        .force('charge', forceManyBody().strength(-2500))
        .force('center', forceCenter(0, 0))
        .force('collide', forceCollide().radius(node => node.type === 'system' ? 120 : 180));

    // Fast-forward the physics simulation synchronously so it doesn't bounce on screen
    for (let i = 0; i < 300; i++) simulation.tick();

    return {
        layoutedNodes: simNodes.map(n => ({ ...n, position: { x: n.x, y: n.y } })),
        layoutedEdges: edges
    };
};

// --- MAIN COMPONENT ---
export default function KnowledgeGraph() {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    
    // Add a ref to track the state signature of the graph
    const graphSignatureRef = useRef("");

    const fetchGraphData = useCallback(async () => {
        try {
            const res = await fetch('http://localhost:8000/graph/');
            const data = await res.json();

            // THE FIX: Check if the topology actually changed before recalculating physics
            const newSignature = `${data.nodes.length}-${data.links.length}`;
            if (graphSignatureRef.current === newSignature) {
                return; // Graph is stable. Do not re-run physics!
            }
            graphSignatureRef.current = newSignature;

            const initialNodes = data.nodes.map(n => {
                const match = n.name.match(/^\[(.*?)\] (.*)$/);
                return {
                    id: n.id,
                    type: n.group,
                    data: { label: match ? match[2] : n.name, topic: match ? match[1] : '' },
                    position: { x: 0, y: 0 },
                };
            });

            const initialEdges = data.links.map(l => ({
                id: `${l.source}-${l.target}`,
                source: l.source,
                target: l.target,
                // Straight lines look much better for network webs than bezier curves
                type: 'straight', 
                animated: l.type === 'contradiction',
                style: {
                    strokeWidth: l.type === 'contradiction' ? 3 : 1.5,
                    stroke: l.type === 'contradiction' ? '#ef4444' : '#334155',
                },
                markerEnd: {
                    type: MarkerType.ArrowClosed,
                    color: l.type === 'contradiction' ? '#ef4444' : '#334155',
                }
            }));

            // Apply D3 Physics
            const { layoutedNodes, layoutedEdges } = applyForceLayout(initialNodes, initialEdges);
            
            setNodes(layoutedNodes);
            setEdges(layoutedEdges);
        } catch (error) {
            console.error("Failed to fetch graph data", error);
        }
    }, [setNodes, setEdges]);

    useEffect(() => {
        fetchGraphData();
        const interval = setInterval(fetchGraphData, 10000);
        return () => clearInterval(interval);
    }, [fetchGraphData]);

    if (nodes.length === 0) return null;

    return (
        <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden h-[600px] relative w-full mb-8 shadow-2xl">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.3 }}
                minZoom={0.1}
                className="bg-slate-950"
            >
                <Background color="#1e293b" gap={30} size={2} />
                <Controls className="fill-slate-400 bg-slate-900 border-slate-700 shadow-xl" />
            </ReactFlow>

            <div className="absolute top-5 left-5 z-10 bg-slate-900/90 px-5 py-3 border border-slate-800 rounded-xl backdrop-blur-md pointer-events-none shadow-lg">
                <span className="font-mono font-bold text-slate-300 tracking-wider uppercase text-xs">
                    Organic Topology View
                </span>
                <div className="flex items-center gap-5 mt-3 text-[11px] font-mono text-slate-400">
                    <span className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></div> Agents
                    </span>
                    <span className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded bg-slate-800 border border-slate-600"></div> Claims
                    </span>
                    <span className="flex items-center gap-2">
                        <div className="w-6 h-[2px] bg-red-500 block relative">
                            <div className="w-2 h-2 rounded-full bg-red-500 absolute -right-1 -top-[3px]"></div>
                        </div> 
                        Collisions
                    </span>
                </div>
            </div>
        </div>
    );
}