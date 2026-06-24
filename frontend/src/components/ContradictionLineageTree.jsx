import { useEffect, useState } from 'react';
import ReactFlow, { Background, Controls, MarkerType } from 'reactflow';
import { fetchLineage } from '../api';

const NODE_STYLES = {
    claim_a:     { background: '#7C2D12', border: '2px solid #EF4444', color: 'white' },
    claim_b:     { background: '#7C2D12', border: '2px solid #EF4444', color: 'white' },
    lca:         { background: '#713F12', border: '2px solid #F59E0B', color: 'white' },  // gold
    ancestry_a:  { background: '#1E293B', border: '1px solid #6366F1', color: '#CBD5E1' },
    ancestry_b:  { background: '#1E293B', border: '1px solid #8B5CF6', color: '#CBD5E1' },
};

export default function ContradictionLineageTree({ contradictionId }) {
    const [data, setData] = useState(null);

    useEffect(() => {
        if (!contradictionId) return;
        fetchLineage(contradictionId).then(setData).catch(console.error);
    }, [contradictionId]);

    if (!data) return <div className="p-6 text-slate-400">Computing causal lineage...</div>;

    // Layout: column A on left, column B on right, LCA pinned to top
    const nodes = data.nodes.map((n, i) => ({
        id: n.id,
        data: { label: `${n.system_name}\n${n.name.slice(0, 60)}` },
        position: computePosition(n, data),
        style: NODE_STYLES[n.group] || NODE_STYLES.ancestry_a,
    }));

    const edges = data.links.map((l, i) => ({
        id: `e-${i}`,
        source: l.source,
        target: l.target,
        animated: l.type === 'contradiction',
        style: {
            stroke: l.type === 'contradiction' ? '#EF4444' :
                    l.type === 'ancestry' && l.chain === 'a' ? '#6366F1' : '#8B5CF6',
            strokeWidth: l.type === 'contradiction' ? 3 : 1.5,
        },
        markerEnd: { type: MarkerType.ArrowClosed },
    }));

    return (
        <div className="h-[600px] bg-slate-950 rounded-2xl border border-slate-800">
            <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
                <h3 className="font-bold text-slate-200">Causal Lineage</h3>
                <div className="flex gap-4 text-xs font-mono">
                    {data.has_shared_ancestor ? (
                        <span className="text-amber-400">
                            ⌥ Shared ancestor — fork at A:{data.fork_distance_a} B:{data.fork_distance_b} hops back
                        </span>
                    ) : (
                        <span className="text-red-400">⚠ No shared ancestor — origin conflict</span>
                    )}
                </div>
            </div>
            <ReactFlow nodes={nodes} edges={edges} fitView>
                <Background color="#1E293B" gap={20} />
                <Controls />
            </ReactFlow>
        </div>
    );
}

// Place ancestry_a on left, ancestry_b on right, LCA at top center
function computePosition(node, data) {
    const yByDepth = node.depth * 120;
    if (node.group === 'lca') return { x: 400, y: 0 };
    if (node.group === 'claim_a' || node.group === 'ancestry_a') return { x: 100, y: yByDepth };
    return { x: 700, y: yByDepth };
}