import { useEffect, useMemo, useState } from 'react';
import { Check, Zap, Circle } from 'lucide-react';
import { fetchCanonGraph, declareCanonValue, promoteCanonCandidate } from '../api';
import GraphView from './CanonGraphView';

export default function Canon() {
    const [graph, setGraph] = useState(null);
    const [err, setErr] = useState(null);
    const [viewMode, setViewMode] = useState('list'); // 'list' | 'graph'
    const [filter, setFilter] = useState('all');       // 'all' | 'declared' | 'candidate' | 'undeclared'
    const [declaring, setDeclaring] = useState(null);  // {store_id, entity} | null

    const load = () => {
        fetchCanonGraph().then(setGraph).catch((e) => setErr(e.message));
    };

    useEffect(load, []);

    if (err) return <ErrorScreen msg={err} />;
    if (!graph) return <LoadingScreen />;

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <div className="h-14 shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border-default)]">
                <h1 className="text-[16px] font-semibold text-[var(--color-text-primary)]">
                    Canon
                </h1>
                <div className="flex items-center gap-6">
                    <SummaryChips summary={graph.summary} />
                    <ViewToggle mode={viewMode} onChange={setViewMode} />
                </div>
            </div>

            {/* Filter bar */}
            <div className="h-11 shrink-0 px-6 flex items-center gap-2 border-b border-[var(--color-border-default)]">
                {['all', 'declared', 'candidate', 'undeclared'].map((f) => (
                    <FilterChip
                        key={f}
                        label={f}
                        active={filter === f}
                        onClick={() => setFilter(f)}
                    />
                ))}
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto">
                {viewMode === 'list' && (
                    <ListView
                        graph={graph}
                        filter={filter}
                        onDeclare={(store_id, entity) => setDeclaring({ store_id, entity, mode: 'declare' })}
                        onPromote={(store_id, entity) => setDeclaring({ store_id, entity, mode: 'promote' })}
                    />
                )}
                {viewMode === 'graph' && (
                    <GraphView
                        graph={graph}
                        onEditEntity={(store_id, entity) =>
                            setDeclaring({ store_id, entity, mode: entity.state === 'declared' ? 'declare' : 'declare' })
                        }
                    />
                )}
            </div>

            {/* Declare panel */}
            {declaring && (
                <DeclarePanel
                    store_id={declaring.store_id}
                    entity={declaring.entity}
                    mode={declaring.mode}
                    onClose={() => setDeclaring(null)}
                    onSaved={() => {
                        setDeclaring(null);
                        load();
                    }}
                />
            )}
        </div>
    );
}

// =====================================================
// Summary chips (top-right of header)
// =====================================================
function SummaryChips({ summary }) {
    return (
        <div className="flex items-center gap-4 font-mono text-[11px]">
            <Chip color="var(--color-ok)" label={`${summary.declared_count} declared`} />
            <Chip color="var(--color-sev-medium)" label={`${summary.candidate_count} candidate`} />
            <Chip color="var(--color-text-tertiary)" label={`${summary.undeclared_count} undeclared`} />
        </div>
    );
}

function Chip({ color, label }) {
    return (
        <span className="inline-flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[var(--color-text-secondary)]">{label}</span>
        </span>
    );
}

// =====================================================
// View toggle
// =====================================================
function ViewToggle({ mode, onChange }) {
    return (
        <div className="flex border border-[var(--color-border-default)]">
            {['list', 'graph'].map((m) => (
                <button
                    key={m}
                    onClick={() => onChange(m)}
                    className={`px-3 py-1 font-mono text-[11px] uppercase tracking-[0.05em] transition-colors ${
                        mode === m
                            ? 'bg-[var(--color-surface-2)] text-[var(--color-text-primary)]'
                            : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
                    }`}
                >
                    {m}
                </button>
            ))}
        </div>
    );
}

function FilterChip({ label, active, onClick }) {
    return (
        <button
            onClick={onClick}
            className={`px-3 h-7 font-mono text-[11px] uppercase tracking-[0.05em] border transition-colors ${
                active
                    ? 'bg-[var(--color-surface-2)] border-[var(--color-accent)] text-[var(--color-text-primary)]'
                    : 'border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
            }`}
        >
            {label}
        </button>
    );
}

// =====================================================
// LIST VIEW
// =====================================================
function ListView({ graph, filter, onDeclare, onPromote }) {
    return (
        <div>
            {graph.stores.map((store) => (
                <StoreSection
                    key={store.store_id}
                    store={store}
                    filter={filter}
                    onDeclare={onDeclare}
                    onPromote={onPromote}
                />
            ))}
        </div>
    );
}

function StoreSection({ store, filter, onDeclare, onPromote }) {
    const filtered = useMemo(
        () => filter === 'all' ? store.entities : store.entities.filter((e) => e.state === filter),
        [store.entities, filter]
    );

    return (
        <div className="border-b border-[var(--color-border-default)]">
            {/* Store header */}
            <div className="px-6 py-3 bg-[var(--color-surface-1)] flex items-center justify-between">
                <div>
                    <span className="font-mono text-[13px] text-[var(--color-text-primary)]">
                        {store.store_name}
                    </span>
                    {store.store_description && (
                        <span className="ml-3 text-[12px] text-[var(--color-text-tertiary)]">
                            {store.store_description}
                        </span>
                    )}
                </div>
                <span className="font-mono text-[11px] text-[var(--color-text-tertiary)]">
                    {filtered.length} of {store.entities.length}
                </span>
            </div>

            {/* Entity rows */}
            {filtered.length === 0 && (
                <div className="px-6 py-4 text-[12px] text-[var(--color-text-tertiary)] italic">
                    No entities match this filter.
                </div>
            )}
            {filtered.map((entity) => (
                <EntityRow
                    key={entity.entity_id}
                    store_id={store.store_id}
                    entity={entity}
                    onDeclare={onDeclare}
                    onPromote={onPromote}
                />
            ))}
        </div>
    );
}

function EntityRow({ store_id, entity, onDeclare, onPromote }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="border-b border-[var(--color-border-default)] last:border-b-0">
            <div className="grid grid-cols-[24px_220px_100px_1fr_180px] gap-3 items-center px-6 py-2.5">
                <StateIcon state={entity.state} />
                <span className="font-mono text-[13px] text-[var(--color-text-primary)]">
                    {entity.canonical_name}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.05em] text-[var(--color-text-tertiary)]">
                    {entity.category || '—'}
                </span>
                <span className="text-[12px] text-[var(--color-text-body)] truncate">
                    {entity.canonical_value || (
                        <span className="text-[var(--color-text-tertiary)] italic">
                            {entity.state === 'candidate'
                                ? `consensus from ${entity.consensus.system_count} system(s), ${entity.consensus.sample_count} samples`
                                : 'no declared value'}
                        </span>
                    )}
                </span>
                <div className="flex items-center gap-2 justify-end">
                    {entity.state === 'candidate' && (
                        <ActionButton onClick={() => onPromote(store_id, entity)}>
                            Promote
                        </ActionButton>
                    )}
                    {entity.state !== 'declared' && (
                        <ActionButton primary onClick={() => onDeclare(store_id, entity)}>
                            Declare
                        </ActionButton>
                    )}
                    {entity.state === 'declared' && (
                        <ActionButton onClick={() => onDeclare(store_id, entity)}>
                            Edit
                        </ActionButton>
                    )}
                    <button
                        onClick={() => setExpanded((v) => !v)}
                        className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] font-mono text-[10px] px-2"
                    >
                        {expanded ? '−' : '+'}
                    </button>
                </div>
            </div>

            {expanded && (
                <div className="px-6 pb-3 pl-[calc(24px+1.5rem+0.75rem)] grid grid-cols-2 gap-6 text-[12px]">
                    <div>
                        <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1">
                            Declared by
                        </div>
                        <div className="text-[var(--color-text-body)]">
                            {entity.declared_by || '—'}
                            {entity.declared_at && (
                                <span className="ml-2 font-mono text-[10px] text-[var(--color-text-tertiary)]">
                                    {entity.declared_at.slice(0, 19).replace('T', ' ')}
                                </span>
                            )}
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1">
                            Consensus
                        </div>
                        <div className="text-[var(--color-text-body)] font-mono text-[11px]">
                            {entity.consensus.strength}
                            <span className="text-[var(--color-text-tertiary)] ml-2">
                                · {entity.consensus.system_count} sys
                                · {entity.consensus.sample_count} samples
                                · conf {entity.consensus.confidence.toFixed(2)}
                            </span>
                        </div>
                    </div>
                    {entity.canonical_claim_text && (
                        <div className="col-span-2">
                            <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1">
                                Full claim text
                            </div>
                            <div className="text-[var(--color-text-body)]">
                                {entity.canonical_claim_text}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function StateIcon({ state }) {
    if (state === 'declared') {
        return <Check size={14} style={{ color: 'var(--color-ok)' }} strokeWidth={2.5} />;
    }
    if (state === 'candidate') {
        return <Zap size={14} style={{ color: 'var(--color-sev-medium)' }} strokeWidth={2} />;
    }
    return <Circle size={12} style={{ color: 'var(--color-text-tertiary)' }} strokeWidth={2} />;
}

function ActionButton({ children, onClick, primary }) {
    return (
        <button
            onClick={onClick}
            className={`h-7 px-3 font-mono text-[11px] uppercase tracking-[0.05em] border transition-colors ${
                primary
                    ? 'bg-[var(--color-accent)] border-[var(--color-accent)] text-[var(--color-surface-0)] hover:bg-[var(--color-accent-hover)]'
                    : 'border-[var(--color-border-strong)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-text-secondary)]'
            }`}
        >
            {children}
        </button>
    );
}

// =====================================================
// DECLARE PANEL (slide-over)
// =====================================================
function DeclarePanel({ store_id, entity, mode = 'declare', onClose, onSaved }) {
    const [value, setValue] = useState(entity.canonical_value || '');
    const [claimText, setClaimText] = useState(entity.canonical_claim_text || '');
    const [declaredBy, setDeclaredBy] = useState('operator');
    const [saving, setSaving] = useState(false);
    const [err, setErr] = useState(null);

    const submit = async () => {
        if (!value.trim()) {
            setErr('Value cannot be empty.');
            return;
        }
        setSaving(true);
        setErr(null);
        try {
            if (mode === 'promote') {
                await promoteCanonCandidate(entity.entity_id, {
                    canonical_value: value.trim(),
                    canonical_claim_text: claimText.trim() || null,
                    declared_by: declaredBy.trim() || 'operator',
                });
            } else {
                await declareCanonValue({
                    store_id,
                    canonical_name: entity.canonical_name,
                    canonical_value: value.trim(),
                    canonical_claim_text: claimText.trim() || null,
                    declared_by: declaredBy.trim() || 'operator',
                });
            }
            onSaved();
        } catch (e) {
            setErr(e.message);
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex justify-end">
            <div
                className="absolute inset-0 bg-black/50"
                onClick={onClose}
            />
            <div className="relative w-[480px] h-full bg-[var(--color-surface-1)] border-l border-[var(--color-border-default)] flex flex-col">
                <div className="h-14 shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border-default)]">
                    <div>
                        <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)]">
                            {mode === 'promote' ? 'Promote candidate' : entity.state === 'declared' ? 'Edit declaration' : 'Declare value'}
                        </div>
                        <div className="font-mono text-[14px] text-[var(--color-text-primary)]">
                            {entity.canonical_name}
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
                    <Field label="Canonical value" required>
                        <textarea
                            value={value}
                            onChange={(e) => setValue(e.target.value)}
                            rows={4}
                            className="w-full px-3 py-2 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] text-[13px] text-[var(--color-text-body)] font-mono focus:border-[var(--color-accent)] focus:outline-none resize-none"
                            placeholder="The truth string agents will receive when they resolve this entity."
                        />
                    </Field>

                    <Field label="Full claim text (optional)">
                        <textarea
                            value={claimText}
                            onChange={(e) => setClaimText(e.target.value)}
                            rows={2}
                            className="w-full px-3 py-2 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] text-[13px] text-[var(--color-text-body)] focus:border-[var(--color-accent)] focus:outline-none resize-none"
                            placeholder="Human-readable full sentence form."
                        />
                    </Field>

                    <Field label="Declared by" required>
                        <input
                            value={declaredBy}
                            onChange={(e) => setDeclaredBy(e.target.value)}
                            className="w-full px-3 py-2 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] text-[13px] text-[var(--color-text-body)] font-mono focus:border-[var(--color-accent)] focus:outline-none"
                            placeholder="operator"
                        />
                    </Field>

                    {entity.state === 'candidate' && (
                        <div className="p-3 bg-[var(--color-surface-2)] border-l-2 border-[var(--color-sev-medium)]">
                            <div className="text-[11px] text-[var(--color-text-secondary)]">
                                This entity has consensus from {entity.consensus.system_count} system{entity.consensus.system_count === 1 ? '' : 's'}
                                {' '}({entity.consensus.sample_count} samples, {entity.consensus.strength}).
                                Declaring a value overrides the consensus and serves the truth string
                                to all subscribing agents.
                            </div>
                        </div>
                    )}

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
                        {saving ? 'Saving…' : mode === 'promote' ? 'Promote' : 'Declare'}
                    </button>
                </div>
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
// Helpers
// =====================================================
function LoadingScreen() {
    return (
        <div className="h-full flex items-center justify-center text-[var(--color-text-tertiary)] font-mono text-[13px]">
            Loading canon…
        </div>
    );
}

function ErrorScreen({ msg }) {
    return (
        <div className="h-full flex items-center justify-center text-[var(--color-sev-critical)] font-mono text-[13px]">
            {msg}
        </div>
    );
}