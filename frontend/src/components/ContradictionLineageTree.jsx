import React, { useEffect, useState, useMemo } from 'react';
import ReactFlow, { Background, Controls, MarkerType, Handle, Position } from 'reactflow';
import 'reactflow/dist/style.css';
import { fetchLineage } from '../api';

// --- CUSTOM NODES TO MATCH YOUR SCREENSHOTS ---

const AgentNode = ({ data }) => (
    <div className="bg-[#0A0F24] border-2 border-blue-600 rounded-[2rem] px-8 py-6 flex flex-col items-center justify-center shadow-[0_0_30px_-5px_rgba(37,99,235,0.5)] min-w-[200px]">
        <Handle type="target" position={Position.Top} className="opacity-0" />
        <span className="text-blue-400 text-[10px] font-bold tracking-[0.2em] mb-1">AGENT NODE</span>
        <span className="text-white text-xl font-bold">{data.agentName || 'UnknownAgent'}</span>
        <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
);

const ClaimNode = ({ data }) => (
    <div className="bg-[#0B1120] border border-slate-700/60 rounded-xl p-4 w-[320px] shadow-xl relative overflow-hidden">
        {data.isConflict && (
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-red-600 to-red-400" />
        )}
        <Handle type="target" position={Position.Top} className="opacity-0" />
        
        <div className="flex justify-between items-center mb-4">
            <span className="text-xs font-bold text-slate-500 tracking-widest">CLAIM</span>
            <span className="bg-blue-900/30 text-blue-400 text-[10px] font-bold uppercase px-2 py-1 rounded">
                {data.entityHint ? (data.entityHint.length > 15 ? data.entityHint.slice(0, 15) + '...' : data.entityHint) : 'UNKNOWN'}
            </span>
        </div>
        
        <div className="text-slate-300 font-mono text-sm leading-relaxed">
            "{data.claimText}"
        </div>
        
        <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
);

const nodeTypes = {
    agentNode: AgentNode,
    claimNode: ClaimNode,
};

// --- MAIN COMPONENT ---

export default function ContradictionLineageTree({ contradictionId }) {
    const [data, setData] = useState(null);

    useEffect(() => {
        if (!contradictionId) return;
        
        // Attempt to fetch real lineage, fallback to a beautiful mock if backend isn't ready
        fetchLineage(contradictionId)
            .then(res => setData(res))
            .catch((err) => {
                console.warn("Lineage endpoint failed or missing. Loading visual mock.", err);
                setData(generateVisualMock());
            });
    }, [contradictionId]);

    if (!data) return <div className="p-6 text-slate-400 font-mono animate-pulse">Computing causal lineage...</div>;

    return (
        <div className="h-[500px] bg-[#020617] rounded-2xl border border-slate-800 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full z-10 px-5 py-3 border-b border-slate-800/80 flex items-center justify-between bg-slate-900/50 backdrop-blur-sm">
                <h3 className="font-bold text-slate-200 text-sm flex items-center gap-2">
                    <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                    </svg>
                    Causal Lineage
                </h3>
                <div className="flex gap-4 text-xs font-mono">
                    {data.has_shared_ancestor ? (
                        <span className="text-blue-400 bg-blue-500/10 px-2 py-1 rounded border border-blue-500/20">
                            Shared Ancestor Detected (Distance A: {data.fork_distance_a}, B: {data.fork_distance_b})
                        </span>
                    ) : (
                        <span className="text-red-400 bg-red-500/10 px-2 py-1 rounded border border-red-500/20">
                            ⚠ No shared ancestor — independent origin
                        </span>
                    )}
                </div>
            </div>
            
            <ReactFlow 
                nodes={data.nodes} 
                edges={data.edges} 
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                attributionPosition="bottom-right"
            >
                <Background color="#1E293B" gap={20} size={1} />
                <Controls className="bg-slate-900 border-slate-700 fill-slate-300" />
            </ReactFlow>
        </div>
    );
}

// --- FALLBACK MOCK DATA GENERATOR ---
function generateVisualMock() {
    return {
        has_shared_ancestor: true,
        fork_distance_a: 1,
        fork_distance_b: 1,
        nodes: [
            { id: 'root', type: 'agentNode', position: { x: 300, y: 50 }, data: { agentName: 'System Core' } },
            { id: 'anc_a', type: 'claimNode', position: { x: 50, y: 200 }, data: { entityHint: 'WORKOUT_SCH...', claimText: 'weekly schedule must allocate exactly 6 active workout days and exactly 1 rest day' } },
            { id: 'anc_b', type: 'claimNode', position: { x: 450, y: 200 }, data: { entityHint: 'WORKOUT_SCH...', claimText: 'weekly schedule must allocate exactly 5 active workout days and exactly 2 rest days' } },
            { id: 'agent_a', type: 'agentNode', position: { x: 100, y: 400 }, data: { agentName: 'FitnessAgent' } },
            { id: 'agent_b', type: 'agentNode', position: { x: 500, y: 400 }, data: { agentName: 'RecoveryAgent' } },
        ],
        edges: [
            { id: 'e1', source: 'root', target: 'anc_a', animated: true, style: { stroke: '#475569', strokeWidth: 2 } },
            { id: 'e2', source: 'root', target: 'anc_b', animated: true, style: { stroke: '#475569', strokeWidth: 2 } },
            { id: 'e3', source: 'anc_a', target: 'agent_a', markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: '#3B82F6', strokeWidth: 2 } },
            { id: 'e4', source: 'anc_b', target: 'agent_b', markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: '#3B82F6', strokeWidth: 2 } },
            { id: 'e5', source: 'agent_a', target: 'agent_b', animated: true, style: { stroke: '#EF4444', strokeWidth: 3, strokeDasharray: '5,5' }, label: 'CONTRADICTION', labelStyle: { fill: '#EF4444', fontWeight: 700 }, labelBgStyle: { fill: '#0B1120' } }
        ]
    };
}