import React, { useEffect, useState } from 'react';
import ReactFlow, { Background, Controls, MarkerType, Handle, Position } from 'reactflow';
import 'reactflow/dist/style.css';
import { GitMerge, AlertCircle, Sparkles } from 'lucide-react';
import { fetchLineageGraph } from '../api';

// =====================================================
// CUSTOM NODE COMPONENTS
// =====================================================

const AgentNode = ({ data }) => (
    <div className="bg-[#0A0F24] border-2 border-blue-600 rounded-3xl px-6 py-4 flex flex-col items-center justify-center shadow-[0_0_30px_-5px_rgba(37,99,235,0.5)] min-w-[180px]">
        <Handle type="target" position={Position.Top} className="opacity-0" />
        <span className="text-blue-400 text-[9px] font-bold tracking-[0.2em] mb-0.5">AGENT NODE</span>
        <span className="text-white text-base font-bold">{data.agentName || 'Unknown'}</span>
        <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
);

const ClaimNode = ({ data }) => {
    // Visual hierarchy:
    //   - LCA claim: indigo top border + sparkle badge
    //   - Conflict roots (depth 0): red gradient top border
    //   - Side A: subtle left border tint
    //   - Side B: subtle right border tint
    //   - Descendants: faded background to push focus to the root row
    const isLCA = data.isLCA;
    const isConflict = data.isConflict;
    const depth = data.depth ?? 0;

    const topBorderClass = isLCA
        ? 'bg-gradient-to-r from-indigo-600 to-violet-500'
        : isConflict
            ? 'bg-gradient-to-r from-red-600 to-red-400'
            : depth > 0
                ? 'bg-gradient-to-r from-slate-700 to-slate-600'
                : 'bg-gradient-to-r from-slate-700 to-slate-600';

    const sideAccent = data.side === 'A'
        ? 'border-l-blue-500/30'
        : data.side === 'B'
            ? 'border-r-blue-500/30'
            : '';

    return (
        <div className={`bg-[#0B1120] border border-slate-700/60 ${sideAccent} rounded-xl p-3.5 w-[300px] shadow-xl relative overflow-hidden ${depth > 0 ? 'opacity-90' : ''}`}>
            <div className={`absolute top-0 left-0 w-full h-1 ${topBorderClass}`} />
            <Handle type="target" position={Position.Top} className="opacity-0" />

            <div className="flex justify-between items-center mb-3">
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-bold text-slate-500 tracking-widest">
                        {isLCA ? 'LCA' : isConflict ? 'ROOT' : 'CLAIM'}
                    </span>
                    {isLCA && <Sparkles className="w-3 h-3 text-indigo-400" />}
                    {isConflict && <AlertCircle className="w-3 h-3 text-red-400" />}
                </div>
                <span className="bg-blue-900/30 text-blue-400 text-[9px] font-bold uppercase px-2 py-0.5 rounded font-mono">
                    {data.entityHint
                        ? (data.entityHint.length > 18 ? data.entityHint.slice(0, 18) + '…' : data.entityHint)
                        : 'UNKNOWN'}
                </span>
            </div>

            <div className="text-slate-300 font-mono text-xs leading-relaxed mb-2.5 line-clamp-3">
                "{data.claimText}"
            </div>

            <div className="flex justify-between items-center text-[10px] font-mono">
                <span className="text-slate-500">{data.systemName || '—'}</span>
                <span className="text-slate-600">
                    depth: <span className={depth === 0 ? 'text-red-400' : 'text-slate-400'}>{depth}</span>
                </span>
            </div>

            <Handle type="source" position={Position.Bottom} className="opacity-0" />
        </div>
    );
};

const nodeTypes = {
    agentNode: AgentNode,
    claimNode: ClaimNode,
};

// =====================================================
// MAIN COMPONENT
// =====================================================

export default function ContradictionLineageTree({ conflict }) {
    const [graph, setGraph] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!conflict) return;
        setGraph(null);
        setError(null);

        fetchLineageGraph(conflict.id)
            .then(setGraph)
            .catch((err) => {
                console.warn("Lineage graph endpoint failed:", err);
                setError("Unable to load lineage graph.");
            });
    }, [conflict?.id]);

    if (error) {
        return (
            <div className="h-[500px] bg-[#020617] rounded-2xl border border-slate-800 flex items-center justify-center">
                <div className="text-center text-slate-500 font-mono text-sm">
                    <AlertCircle className="w-8 h-8 mx-auto mb-3 opacity-40" />
                    {error}
                </div>
            </div>
        );
    }

    if (!graph) {
        return (
            <div className="h-[500px] bg-[#020617] rounded-2xl border border-slate-800 flex items-center justify-center">
                <div className="text-slate-400 font-mono text-sm animate-pulse">
                    Computing causal lineage...
                </div>
            </div>
        );
    }

    // Layout edges need MarkerType objects, not plain strings — ReactFlow quirk
    const edgesWithMarkers = (graph.edges || []).map(e => ({
        ...e,
        markerEnd: e.markerEnd
            ? { type: MarkerType.ArrowClosed, color: e.style?.stroke || '#475569' }
            : undefined,
    }));

    return (
        <div className="h-[560px] bg-[#020617] rounded-2xl border border-slate-800 relative overflow-hidden">
            {/* Header */}
            <div className="absolute top-0 left-0 w-full z-10 px-5 py-3 border-b border-slate-800/80 flex items-center justify-between bg-slate-900/70 backdrop-blur-sm">
                <h3 className="font-bold text-slate-200 text-sm flex items-center gap-2">
                    <GitMerge className="w-4 h-4 text-blue-500" />
                    Causal Lineage
                    <span className="text-[10px] font-mono text-slate-500 ml-2">
                        {graph.node_count} nodes · {graph.edge_count} edges
                    </span>
                </h3>
                <div className="flex gap-2 text-[10px] font-mono">
                    {graph.has_shared_ancestor ? (
                        <span className="text-indigo-300 bg-indigo-500/10 px-2.5 py-1 rounded border border-indigo-500/20 flex items-center gap-1.5">
                            <Sparkles className="w-3 h-3" />
                            LCA found · fork A:{graph.fork_distance_a} / B:{graph.fork_distance_b}
                        </span>
                    ) : (
                        <span className="text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded border border-amber-500/20">
                            ⚠ No shared ancestor — independent origin
                        </span>
                    )}
                </div>
            </div>

            <ReactFlow
                nodes={graph.nodes}
                edges={edgesWithMarkers}
                nodeTypes={nodeTypes}
                defaultViewport={{ x: 0, y: 0, zoom: 0.6 }}
                onInit={(instance) => {
                    // One-shot fit on first render; never re-fits when nodes/edges change
                    setTimeout(() => instance.fitView({ padding: 0.25, duration: 0 }), 50);
                }}
                minZoom={0.2}
                maxZoom={2}
                nodesDraggable={true}
                nodesConnectable={false}
                elementsSelectable={true}
                panOnDrag={true}
                panOnScroll={false}
                zoomOnScroll={true}
                zoomOnPinch={true}
                zoomOnDoubleClick={true}
                proOptions={{ hideAttribution: true }}
            >
                <Background color="#1E293B" gap={24} size={1} />
                <Controls
                    showInteractive={false}
                    className="bg-slate-900 border border-slate-700 rounded-lg shadow-xl [&>button]:bg-slate-900 [&>button]:border-slate-700 [&>button]:text-slate-300 [&>button:hover]:bg-slate-800"
                />
            </ReactFlow>
        </div>
    );
}