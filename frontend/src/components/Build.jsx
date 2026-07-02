import { useEffect, useMemo, useState } from 'react';
import ReactFlow, {
    Background,
    Controls,
    Handle,
    Position,
    useNodesState,
    useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Plus, Copy, Check as CheckIcon } from 'lucide-react';
import {
    fetchSystems,
    fetchSystemScore,
    fetchSystemSubscriptions,
    fetchCanonStores,
    createAgent,
} from '../api';

const HIDDEN_PREFIXES = ['Isolation', 'CanonAdmin', 'SmokeTest', 'DashboardViewer'];
const isHidden = (name) => HIDDEN_PREFIXES.some((p) => name.startsWith(p));

// =====================================================
// Layout
// =====================================================
const CENTER_X = 0;
const CENTER_Y = 0;
const RADIUS = 320;
const CARD_W = 220;
const CARD_H = 96;

function radialPosition(i, n) {
    if (n === 0) return { x: 0, y: 0 };
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    return {
        x: CENTER_X + RADIUS * Math.cos(angle) - CARD_W / 2,
        y: CENTER_Y + RADIUS * Math.sin(angle) - CARD_H / 2,
    };
}

// =====================================================
// Custom node types
// =====================================================
function FleetCenterNode() {
    return (
        <div
            className="flex items-center justify-center border-2 bg-[var(--color-surface-1)]"
            style={{
                width: 140,
                height: 140,
                borderRadius: '50%',
                borderColor: 'var(--color-accent)',
            }}
        >
            <Handle type="source" position={Position.Top} style={{ opacity: 0 }} />
            <div className="text-center">
                <div className="text-[9px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1">
                    Fleet
                </div>
                <div className="font-mono text-[13px] text-[var(--color-text-primary)]">
                    demo-fitness
                </div>
            </div>
        </div>
    );
}

function AgentCardNode({ data }) {
    return (
        <div
            className="bg-[var(--color-surface-1)] border transition-all cursor-pointer hover:border-[var(--color-accent)]"
            style={{
                width: CARD_W,
                height: CARD_H,
                borderColor: data.isNew
                    ? 'var(--color-sev-medium)'
                    : 'var(--color-border-strong)',
            }}
            onClick={() => data.onClick?.()}
        >
            <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
            <div className="p-3 h-full flex flex-col">
                <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-[13px] text-[var(--color-text-primary)] truncate">
                        {data.name}
                    </span>
                    <HealthChip status={data.healthStatus} score={data.score} />
                </div>
                <div className="flex items-center gap-2 mb-auto">
                    <span className="font-mono text-[10px] uppercase tracking-[0.05em] text-[var(--color-text-tertiary)]">
                        {data.provider}
                    </span>
                </div>
                <div className="flex items-center justify-between mt-1">
                    <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
                        {data.subCount != null
                            ? `${data.subCount} sub${data.subCount === 1 ? '' : 's'}`
                            : '—'}
                    </span>
                    {data.isNew && (
                        <span className="font-mono text-[9px] uppercase tracking-[0.05em] text-[var(--color-sev-medium)]">
                            restart to activate
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}

function HealthChip({ status, score }) {
    if (status === 'loading') {
        return <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">…</span>;
    }
    if (status === 'not_running') {
        return <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">◦</span>;
    }
    if (score == null) return null;
    const pct = Math.round(score * 100);
    const color =
        pct >= 90 ? 'var(--color-ok)'
        : pct >= 70 ? 'var(--color-sev-medium)'
        : 'var(--color-sev-high)';
    return (
        <span className="font-mono text-[10px]" style={{ color }}>
            {pct}%
        </span>
    );
}

const nodeTypes = { fleetCenter: FleetCenterNode, agentCard: AgentCardNode };

// =====================================================
// Main component
// =====================================================
export default function Build() {
    const [systems, setSystems] = useState([]);
    const [enriched, setEnriched] = useState({}); // { [id]: { score, subs } }
    const [creating, setCreating] = useState(false);
    const [tokenModal, setTokenModal] = useState(null);
    const [newlyCreatedIds, setNewlyCreatedIds] = useState(new Set());
    const [err, setErr] = useState(null);
    const [selectedAgent, setSelectedAgent] = useState(null);

    const load = () => {
        fetchSystems()
            .then((list) => {
                const visible = list.filter((s) => !isHidden(s.name));
                setSystems(visible);
                // Load enrichment for each in parallel
                visible.forEach((s) => {
                    Promise.all([
                        fetchSystemScore(s.id).catch(() => null),
                        fetchSystemSubscriptions(s.id).catch(() => null),
                    ]).then(([score, subs]) => {
                        setEnriched((prev) => ({
                            ...prev,
                            [s.id]: { score, subs },
                        }));
                    });
                });
            })
            .catch((e) => setErr(e.message));
    };

    useEffect(load, []);

    // Build canvas
    const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
        const nodes = [
            {
                id: 'fleet-center',
                type: 'fleetCenter',
                position: { x: -70, y: -70 },
                draggable: false,
            },
        ];
        const edges = [];
        systems.forEach((s, i) => {
            const pos = radialPosition(i, systems.length);
            const e = enriched[s.id];
            const healthStatus =
                !e ? 'loading'
                : !e.score ? 'not_running'
                : 'has_score';
            nodes.push({
                id: `agent:${s.id}`,
                type: 'agentCard',
                position: pos,
                data: {
                    name: s.name,
                    provider: s.provider,
                    healthStatus,
                    score: e?.score?.score,
                    subCount: e?.subs?.subscriptions?.length,
                    isNew: newlyCreatedIds.has(s.id),
                    onClick: () => setSelectedAgent(s),
                },
                draggable: false,
            });
            edges.push({
                id: `edge:fleet:${s.id}`,
                source: 'fleet-center',
                target: `agent:${s.id}`,
                type: 'straight',
                style: {
                    stroke: 'var(--color-border-strong)',
                    strokeWidth: 1,
                    opacity: 0.3,
                },
            });
        });
        return { nodes, edges };
    }, [systems, enriched, newlyCreatedIds]);

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    // Re-set when systems/enrichment change
    useEffect(() => {
        setNodes(initialNodes);
        setEdges(initialEdges);
    }, [initialNodes, initialEdges, setNodes, setEdges]);

    if (err) {
        return (
            <div className="h-full flex items-center justify-center text-[var(--color-sev-critical)] font-mono text-[13px]">
                {err}
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <div className="h-14 shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border-default)]">
                <div>
                    <h1 className="text-[16px] font-semibold text-[var(--color-text-primary)]">
                        Build
                    </h1>
                    <p className="text-[11px] text-[var(--color-text-tertiary)] mt-0.5">
                        Fleet authoring canvas · {systems.length} agent{systems.length === 1 ? '' : 's'}
                    </p>
                </div>
                <button
                    onClick={() => setCreating(true)}
                    className="h-9 px-4 flex items-center gap-2 bg-[var(--color-accent)] text-[var(--color-surface-0)] font-mono text-[11px] uppercase tracking-[0.05em] hover:bg-[var(--color-accent-hover)]"
                >
                    <Plus size={14} strokeWidth={2.5} />
                    New agent
                </button>
            </div>

            {/* Canvas */}
            <div className="flex-1 relative">
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
                >
                    <Background
                        color="var(--color-border-default)"
                        gap={24}
                        size={1}
                    />
                    <Controls showInteractive={false} />
                </ReactFlow>
            </div>

            {creating && (
                <CreateAgentPanel
                    onClose={() => setCreating(false)}
                    onCreated={(response) => {
                        setCreating(false);
                        setTokenModal(response);
                        setNewlyCreatedIds((prev) => new Set([...prev, response.id]));
                        load();
                    }}
                />
            )}

            {tokenModal && (
                <TokenDisclosureModal
                    response={tokenModal}
                    onClose={() => setTokenModal(null)}
                />
            )}

            {selectedAgent && (
                <AgentDetailPanel
                    system={selectedAgent}
                    enrichment={enriched[selectedAgent.id]}
                    onClose={() => setSelectedAgent(null)}
                />
            )}
        </div>
    );
}

// =====================================================
// CREATE AGENT PANEL
// =====================================================
function CreateAgentPanel({ onClose, onCreated }) {
    const [name, setName] = useState('');
    const [provider, setProvider] = useState('openai');
    const [description, setDescription] = useState('');
    const [kbYaml, setKbYaml] = useState(DEFAULT_KB_TEMPLATE);
    const [stores, setStores] = useState([]);
    const [selectedStoreIds, setSelectedStoreIds] = useState(new Set());
    const [saving, setSaving] = useState(false);
    const [err, setErr] = useState(null);

    useEffect(() => {
        fetchCanonStores().then((list) => {
            setStores(list);
            // Auto-select the default store if it exists
            const def = list.find((s) => s.store_name === 'default');
            if (def) setSelectedStoreIds(new Set([def.store_id]));
        });
    }, []);

    const submit = async () => {
        if (!name.trim()) {
            setErr('Name is required.');
            return;
        }
        if (!/^[A-Z][a-zA-Z0-9]+$/.test(name.trim())) {
            setErr('Name must start with an uppercase letter and be CamelCase.');
            return;
        }
        setSaving(true);
        setErr(null);
        try {
            const response = await createAgent({
                name: name.trim(),
                provider,
                description: description.trim() || null,
                kb_yaml: kbYaml,
                subscriptions: [...selectedStoreIds].map((store_id) => ({
                    store_id,
                    precedence_rank: 0,
                })),
            });
            onCreated(response);
        } catch (e) {
            setErr(e.message);
            setSaving(false);
        }
    };

    const toggleStore = (id) => {
        setSelectedStoreIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    return (
        <div className="fixed inset-0 z-50 flex justify-end">
            <div className="absolute inset-0 bg-black/50" onClick={onClose} />
            <div className="relative w-[560px] h-full bg-[var(--color-surface-1)] border-l border-[var(--color-border-default)] flex flex-col">
                <div className="h-14 shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border-default)]">
                    <div>
                        <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)]">
                            New agent
                        </div>
                        <div className="font-mono text-[14px] text-[var(--color-text-primary)]">
                            Register in demo-fitness
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-[20px] leading-none"
                    >
                        ×
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-5">
                    <Field label="Name" required>
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. SleepAgent"
                            className="w-full px-3 py-2 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] text-[13px] text-[var(--color-text-body)] font-mono focus:border-[var(--color-accent)] focus:outline-none"
                        />
                        <div className="mt-1 text-[10px] text-[var(--color-text-tertiary)] font-mono">
                            CamelCase. Determines KB filename and container name.
                        </div>
                    </Field>

                    <Field label="Provider">
                        <select
                            value={provider}
                            onChange={(e) => setProvider(e.target.value)}
                            className="w-full px-3 py-2 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] text-[13px] text-[var(--color-text-body)] font-mono focus:border-[var(--color-accent)] focus:outline-none"
                        >
                            <option value="openai">openai</option>
                            <option value="anthropic">anthropic</option>
                            <option value="internal">internal</option>
                        </select>
                    </Field>

                    <Field label="Description">
                        <input
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="What does this agent do?"
                            className="w-full px-3 py-2 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] text-[13px] text-[var(--color-text-body)] focus:border-[var(--color-accent)] focus:outline-none"
                        />
                    </Field>

                    <Field label="Knowledge base (YAML)" required>
                        <textarea
                            value={kbYaml}
                            onChange={(e) => setKbYaml(e.target.value)}
                            rows={14}
                            className="w-full px-3 py-2 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] text-[12px] text-[var(--color-text-body)] font-mono focus:border-[var(--color-accent)] focus:outline-none resize-none"
                        />
                        <div className="mt-1 text-[10px] text-[var(--color-text-tertiary)] font-mono">
                            Written to /app/demo/kb/&lt;name_snake&gt;.yaml
                        </div>
                    </Field>

                    <Field label="Canon store subscriptions">
                        <div className="border border-[var(--color-border-default)]">
                            {stores.length === 0 ? (
                                <div className="px-3 py-4 text-[12px] text-[var(--color-text-tertiary)] italic">
                                    Loading stores…
                                </div>
                            ) : (
                                stores.map((s) => (
                                    <label
                                        key={s.store_id}
                                        className="flex items-center gap-3 px-3 py-2 border-b border-[var(--color-border-default)] last:border-b-0 cursor-pointer hover:bg-[var(--color-surface-2)]"
                                    >
                                        <input
                                            type="checkbox"
                                            checked={selectedStoreIds.has(s.store_id)}
                                            onChange={() => toggleStore(s.store_id)}
                                        />
                                        <span className="font-mono text-[12px] text-[var(--color-text-primary)]">
                                            {s.store_name}
                                        </span>
                                        <span className="font-mono text-[10px] text-[var(--color-text-tertiary)] ml-auto">
                                            {s.entity_count} entities
                                        </span>
                                    </label>
                                ))
                            )}
                        </div>
                    </Field>

                    {err && (
                        <div className="text-[12px] text-[var(--color-sev-critical)] font-mono">
                            {err}
                        </div>
                    )}
                </div>

                <div className="h-14 shrink-0 px-6 flex items-center justify-end gap-3 border-t border-[var(--color-border-default)]">
                    <button
                        onClick={onClose}
                        disabled={saving}
                        className="h-8 px-4 font-mono text-[11px] uppercase tracking-[0.05em] border border-[var(--color-border-strong)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={submit}
                        disabled={saving}
                        className="h-8 px-4 font-mono text-[11px] uppercase tracking-[0.05em] bg-[var(--color-accent)] text-[var(--color-surface-0)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
                    >
                        {saving ? 'Registering…' : 'Register'}
                    </button>
                </div>
            </div>
        </div>
    );
}

// =====================================================
// TOKEN DISCLOSURE MODAL
// =====================================================
function TokenDisclosureModal({ response, onClose }) {
    const [copied, setCopied] = useState(false);

    const copy = async () => {
        await navigator.clipboard.writeText(response.api_token);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70">
            <div className="w-[560px] bg-[var(--color-surface-1)] border border-[var(--color-border-strong)]">
                <div className="p-6 border-b border-[var(--color-border-default)]">
                    <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-sev-medium)] mb-1">
                        One-time token disclosure
                    </div>
                    <div className="font-mono text-[16px] text-[var(--color-text-primary)]">
                        {response.name}
                    </div>
                </div>

                <div className="p-6 space-y-4">
                    <div className="text-[13px] text-[var(--color-text-body)] leading-relaxed">
                        Copy this API token now. It is stored only as a hash on the server and
                        cannot be retrieved later. The agent uses this token to authenticate
                        against Orqestra.
                    </div>

                    <div className="relative">
                        <pre className="w-full p-3 pr-14 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] font-mono text-[11px] text-[var(--color-text-primary)] break-all whitespace-pre-wrap">
                            {response.api_token}
                        </pre>
                        <button
                            onClick={copy}
                            className="absolute top-2 right-2 h-8 w-8 flex items-center justify-center border border-[var(--color-border-strong)] text-[var(--color-text-body)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
                        >
                            {copied ? <CheckIcon size={14} /> : <Copy size={14} />}
                        </button>
                    </div>

                    <div className="text-[11px] text-[var(--color-text-tertiary)] font-mono">
                        KB written to: {response.kb_path}
                    </div>

                    {response.kb_warnings?.length > 0 && (
                        <div className="p-3 bg-[var(--color-surface-2)] border-l-2 border-[var(--color-sev-medium)] space-y-1">
                            <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-sev-medium)]">
                                Warnings
                            </div>
                            {response.kb_warnings.map((w, i) => (
                                <div key={i} className="text-[11px] text-[var(--color-text-body)] font-mono">
                                    {w}
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="p-3 bg-[var(--color-surface-2)] border-l-2 border-[var(--color-accent)]">
                        <div className="text-[11px] text-[var(--color-text-body)]">
                            <strong className="text-[var(--color-text-primary)]">Next step:</strong>{' '}
                            add this agent's service to docker-compose.yml with the token
                            in its env file, then run <code className="font-mono text-[var(--color-accent)]">docker compose up -d {response.name.toLowerCase()}</code> to
                            activate.
                        </div>
                    </div>
                </div>

                <div className="p-6 border-t border-[var(--color-border-default)] flex justify-end">
                    <button
                        onClick={onClose}
                        className="h-9 px-5 font-mono text-[11px] uppercase tracking-[0.05em] bg-[var(--color-accent)] text-[var(--color-surface-0)] hover:bg-[var(--color-accent-hover)]"
                    >
                        I've saved the token
                    </button>
                </div>
            </div>
        </div>
    );
}

// =====================================================
// AGENT DETAIL PANEL (readonly for existing cards)
// =====================================================
function AgentDetailPanel({ system, enrichment, onClose }) {
    return (
        <div className="fixed inset-0 z-50 flex justify-end">
            <div className="absolute inset-0 bg-black/50" onClick={onClose} />
            <div className="relative w-[420px] h-full bg-[var(--color-surface-1)] border-l border-[var(--color-border-default)] flex flex-col">
                <div className="h-14 shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border-default)]">
                    <div>
                        <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)]">
                            Agent
                        </div>
                        <div className="font-mono text-[14px] text-[var(--color-text-primary)]">
                            {system.name}
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-[20px] leading-none"
                    >
                        ×
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-5">
                    <MetaRow label="Provider" value={system.provider} />
                    <MetaRow label="Description" value={system.description || '—'} />
                    <MetaRow
                        label="Coherence score"
                        value={
                            enrichment?.score?.score != null
                                ? `${Math.round(enrichment.score.score * 100)}%`
                                : 'not running or no data'
                        }
                    />
                    <MetaRow
                        label="Subscriptions"
                        value={
                            enrichment?.subs?.subscriptions?.length
                                ? enrichment.subs.subscriptions
                                      .map((s) => `${s.store_name} (rank ${s.precedence_rank})`)
                                      .join(', ')
                                : '—'
                        }
                    />

                    <div className="pt-4 text-[11px] text-[var(--color-text-tertiary)]">
                        For full KB, canon lookups, and recent claims, see this agent in{' '}
                        <a href="/estate" className="text-[var(--color-accent)] hover:underline">
                            Estate view
                        </a>
                        .
                    </div>
                </div>
            </div>
        </div>
    );
}

function MetaRow({ label, value }) {
    return (
        <div>
            <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1">
                {label}
            </div>
            <div className="text-[13px] text-[var(--color-text-body)] font-mono">
                {value}
            </div>
        </div>
    );
}

function Field({ label, required, children }) {
    return (
        <div>
            <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1.5">
                {label} {required && <span className="text-[var(--color-sev-high)]">*</span>}
            </div>
            {children}
        </div>
    );
}

// =====================================================
// Default KB template
// =====================================================
const DEFAULT_KB_TEMPLATE = `agent_identity: |
  You are <AgentName>, a <role> for <purpose>.

org_policy: |
  <One-line policy this agent must follow.>

valid_entities:
  - <entity_1>
  - <entity_2>

data_access:
  read: []
  write: []

domain_knowledge:
  <topic>: |
    <knowledge summary>
`;