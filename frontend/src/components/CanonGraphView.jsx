import { useMemo, useCallback } from 'react';
import ReactFlow, {
    Background,
    Controls,
    Handle,
    Position,
    useNodesState,
    useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';

// =====================================================
// Layout constants
// =====================================================
const STORE_RADIUS = 60;
const ORBIT_RADIUS = 220;
const STORE_SPACING_X = 700; // horizontal gap between stores if multiple

// Color by entity state (matches list view semantics)
const STATE_COLOR = {
    declared: 'var(--color-ok)',
    candidate: 'var(--color-sev-medium)',
    undeclared: 'var(--color-text-tertiary)',
};

// =====================================================
// Custom nodes
// =====================================================
function StoreNode({ data }) {
    return (
        <div
            className="flex items-center justify-center border-2 bg-[var(--color-surface-1)]"
            style={{
                width: STORE_RADIUS * 2,
                height: STORE_RADIUS * 2,
                borderRadius: '50%',
                borderColor: 'var(--color-accent)',
            }}
        >
            <Handle type="source" position={Position.Top} style={{ opacity: 0 }} />
            <div className="text-center px-3">
                <div className="text-[9px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1">
                    Store
                </div>
                <div className="font-mono text-[13px] text-[var(--color-text-primary)] leading-tight">
                    {data.name}
                </div>
                <div className="font-mono text-[10px] text-[var(--color-text-tertiary)] mt-1">
                    {data.entityCount} entities
                </div>
            </div>
        </div>
    );
}

function EntityNode({ data }) {
    const color = STATE_COLOR[data.state];
    return (
        <div
            className="relative group cursor-pointer"
            onClick={() => data.onClick?.()}
        >
            <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
            <div
                className="w-16 h-16 flex items-center justify-center border-2 bg-[var(--color-surface-1)] transition-all group-hover:scale-110"
                style={{
                    borderRadius: '50%',
                    borderColor: color,
                }}
            >
                <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: color }}
                />
            </div>
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 font-mono text-[10px] text-[var(--color-text-body)] whitespace-nowrap text-center">
                {data.name}
            </div>

            {/* Hover card */}
            <div className="absolute left-full top-1/2 -translate-y-1/2 ml-3 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
                <div className="w-72 p-3 bg-[var(--color-surface-2)] border border-[var(--color-border-strong)] shadow-lg">
                    <div className="flex items-center gap-2 mb-2">
                        <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ backgroundColor: color }}
                        />
                        <span className="font-mono text-[11px] uppercase tracking-[0.05em] text-[var(--color-text-secondary)]">
                            {data.state}
                        </span>
                        {data.category && (
                            <span className="font-mono text-[9px] uppercase tracking-[0.05em] text-[var(--color-text-tertiary)] ml-auto">
                                {data.category}
                            </span>
                        )}
                    </div>
                    <div className="font-mono text-[12px] text-[var(--color-text-primary)] mb-2">
                        {data.name}
                    </div>
                    <div className="text-[12px] text-[var(--color-text-body)] leading-relaxed">
                        {data.value || (
                            <span className="text-[var(--color-text-tertiary)] italic">
                                {data.state === 'candidate'
                                    ? `consensus: ${data.consensus.strength} · ${data.consensus.system_count} sys · ${data.consensus.sample_count} samples`
                                    : 'no declared value'}
                            </span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

const nodeTypes = { store: StoreNode, entity: EntityNode };

// =====================================================
// Layout: radial per store, stores laid out horizontally
// =====================================================
function buildLayout(graph, onEntityClick) {
    const nodes = [];
    const edges = [];

    graph.stores.forEach((store, storeIdx) => {
        const cx = storeIdx * STORE_SPACING_X;
        const cy = 0;

        nodes.push({
            id: `store:${store.store_id}`,
            type: 'store',
            position: { x: cx - STORE_RADIUS, y: cy - STORE_RADIUS },
            data: {
                name: store.store_name,
                entityCount: store.entities.length,
            },
            draggable: false,
        });

        const n = store.entities.length;
        store.entities.forEach((entity, i) => {
            // Start from top (−π/2), go clockwise
            const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
            const ex = cx + ORBIT_RADIUS * Math.cos(angle);
            const ey = cy + ORBIT_RADIUS * Math.sin(angle);

            nodes.push({
                id: `entity:${entity.entity_id}`,
                type: 'entity',
                position: { x: ex - 32, y: ey - 32 }, // node is 64x64 including padding
                data: {
                    name: entity.canonical_name,
                    state: entity.state,
                    category: entity.category,
                    value: entity.canonical_value,
                    consensus: entity.consensus,
                    onClick: () => onEntityClick(store.store_id, entity),
                },
                draggable: false,
            });

            edges.push({
                id: `edge:${store.store_id}:${entity.entity_id}`,
                source: `store:${store.store_id}`,
                target: `entity:${entity.entity_id}`,
                type: 'straight',
                style: {
                    stroke: STATE_COLOR[entity.state],
                    strokeWidth: 1,
                    opacity: 0.4,
                },
            });
        });
    });

    return { nodes, edges };
}

// =====================================================
// Main component
// =====================================================
export default function CanonGraphView({ graph, onEditEntity }) {
    const initialLayout = useMemo(
        () => buildLayout(graph, onEditEntity),
        [graph, onEditEntity]
    );

    const [nodes, , onNodesChange] = useNodesState(initialLayout.nodes);
    const [edges, , onEdgesChange] = useEdgesState(initialLayout.edges);

    return (
        <div className="h-full w-full relative">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.3 }}
                minZoom={0.3}
                maxZoom={2}
                proOptions={{ hideAttribution: true }}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={true}
            >
                <Background
                    color="var(--color-border-default)"
                    gap={24}
                    size={1}
                />
                <Controls
                    showInteractive={false}
                    style={{
                        button: {
                            backgroundColor: 'var(--color-surface-1)',
                            borderColor: 'var(--color-border-default)',
                            color: 'var(--color-text-body)',
                        },
                    }}
                />
            </ReactFlow>
        </div>
    );
}