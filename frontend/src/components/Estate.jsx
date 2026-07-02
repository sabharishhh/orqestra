import { useEffect, useMemo, useState } from 'react';
import {
    fetchSystems,
    fetchSystemSubscriptions,
    fetchSystemRecentClaims,
    fetchSystemKB,
    fetchSystemCanonLookups,
    fetchSystemScore,
} from '../api';

// Hide admin/test systems from the estate view.
// Ledger #10: proper fix is a system_type column; this is cosmetic for now.
const HIDDEN_PREFIXES = ['Isolation', 'CanonAdmin', 'SmokeTest', 'DashboardViewer'];
const isHidden = (name) => HIDDEN_PREFIXES.some((p) => name.startsWith(p));

export default function Estate() {
    const [systems, setSystems] = useState(null);
    const [selectedId, setSelectedId] = useState(null);
    const [loadErr, setLoadErr] = useState(null);

    useEffect(() => {
        fetchSystems()
            .then((list) => {
                const visible = list.filter((s) => !isHidden(s.name));
                setSystems(visible);
                if (visible.length > 0) setSelectedId(visible[0].id);
            })
            .catch((e) => setLoadErr(e.message));
    }, []);

    if (loadErr) {
        return (
            <div className="h-full flex items-center justify-center text-[var(--color-sev-critical)] font-mono text-[13px]">
                Failed to load estate: {loadErr}
            </div>
        );
    }

    if (!systems) {
        return (
            <div className="h-full flex items-center justify-center text-[var(--color-text-tertiary)] font-mono text-[13px]">
                Loading estate…
            </div>
        );
    }

    if (systems.length === 0) {
        return (
            <div className="h-full flex items-center justify-center text-[var(--color-text-tertiary)]">
                No agents registered in this org.
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col">
            {/* header */}
            <div className="h-14 shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border-default)]">
                <h1 className="text-[16px] font-semibold text-[var(--color-text-primary)]">
                    Agent Estate
                </h1>
                <span className="font-mono text-[12px] text-[var(--color-text-tertiary)]">
                    {systems.length} agent{systems.length === 1 ? '' : 's'}
                </span>
            </div>

            {/* master + detail */}
            <div className="flex-1 flex overflow-hidden">
                <AgentList
                    systems={systems}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                />
                <AgentDetail systemId={selectedId} />
            </div>
        </div>
    );
}

// =====================================================
// LEFT PANE — agent list
// =====================================================
function AgentList({ systems, selectedId, onSelect }) {
    return (
        <div className="w-80 shrink-0 border-r border-[var(--color-border-default)] overflow-y-auto">
            {systems.map((s) => (
                <AgentListRow
                    key={s.id}
                    system={s}
                    selected={s.id === selectedId}
                    onClick={() => onSelect(s.id)}
                />
            ))}
        </div>
    );
}

function AgentListRow({ system, selected, onClick }) {
    const [score, setScore] = useState(null);

    useEffect(() => {
        fetchSystemScore(system.id).then(setScore).catch(() => setScore({ score: null }));
    }, [system.id]);

    return (
        <button
            onClick={onClick}
            className={`w-full text-left px-4 py-3 border-b border-[var(--color-border-default)] transition-colors ${
                selected
                    ? 'bg-[var(--color-surface-2)] border-l-2 border-l-[var(--color-accent)]'
                    : 'hover:bg-[var(--color-surface-1)] border-l-2 border-l-transparent'
            }`}
        >
            <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-[13px] text-[var(--color-text-primary)]">
                    {system.name}
                </span>
                <ScoreBadge score={score?.score} />
            </div>
            <div className="text-[11px] text-[var(--color-text-tertiary)] font-mono">
                {system.provider}
            </div>
        </button>
    );
}

function ScoreBadge({ score }) {
    if (score == null) {
        return <span className="font-mono text-[10px] text-[var(--color-text-disabled)]">—</span>;
    }
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

// =====================================================
// RIGHT PANE — agent detail
// =====================================================
function AgentDetail({ systemId }) {
    if (!systemId) {
        return (
            <div className="flex-1 flex items-center justify-center text-[var(--color-text-tertiary)] font-mono text-[13px]">
                Select an agent
            </div>
        );
    }

    return (
        <div className="flex-1 overflow-y-auto">
            <KBSection systemId={systemId} />
            <SubscriptionsSection systemId={systemId} />
            <CanonLookupsSection systemId={systemId} />
            <RecentClaimsSection systemId={systemId} />
        </div>
    );
}

// -----------------------------
// KB section
// -----------------------------
function KBSection({ systemId }) {
    const [kb, setKb] = useState(null);
    const [err, setErr] = useState(null);
    const [showYaml, setShowYaml] = useState(false);

    useEffect(() => {
        setKb(null);
        setErr(null);
        setShowYaml(false);
        fetchSystemKB(systemId).then(setKb).catch((e) => setErr(e.message));
    }, [systemId]);

    return (
        <DetailSection title="Knowledge base" subtitle={kb?.kb_path}>
            {err && <ErrorLine msg={err} />}
            {!err && !kb && <LoadingLine />}
            {kb && !kb.kb_available && (
                <div className="text-[12px] text-[var(--color-text-tertiary)] italic">
                    No KB file on disk. {kb.reason}
                </div>
            )}
            {kb?.kb_available && (
                <>
                    <FieldRow label="Identity">
                        <div className="text-[13px] text-[var(--color-text-body)] leading-relaxed">
                            {kb.kb.agent_identity || '—'}
                        </div>
                    </FieldRow>
                    <FieldRow label="Org policy">
                        <div className="text-[13px] text-[var(--color-text-body)] leading-relaxed">
                            {kb.kb.org_policy || '—'}
                        </div>
                    </FieldRow>
                    <FieldRow label="Valid entities">
                        <div className="flex flex-wrap gap-1.5">
                            {(kb.kb.valid_entities || []).map((e) => (
                                <span
                                    key={e}
                                    className="font-mono text-[11px] px-2 py-0.5 bg-[var(--color-surface-2)] text-[var(--color-text-body)]"
                                >
                                    {e}
                                </span>
                            ))}
                        </div>
                    </FieldRow>
                    <FieldRow label="Domain knowledge">
                        <div className="flex flex-wrap gap-1.5">
                            {(kb.kb.domain_knowledge_keys || []).map((k) => (
                                <span
                                    key={k}
                                    className="font-mono text-[11px] px-2 py-0.5 bg-[var(--color-surface-2)] text-[var(--color-text-secondary)]"
                                >
                                    {k}
                                </span>
                            ))}
                        </div>
                    </FieldRow>
                    <button
                        onClick={() => setShowYaml((v) => !v)}
                        className="mt-2 text-[11px] text-[var(--color-accent)] hover:underline"
                    >
                        {showYaml ? 'Hide raw YAML' : 'Show raw YAML'}
                    </button>
                    {showYaml && (
                        <pre className="mt-2 p-3 bg-[var(--color-surface-0)] border border-[var(--color-border-default)] font-mono text-[11px] text-[var(--color-text-secondary)] overflow-x-auto max-h-96 overflow-y-auto">
                            {kb.raw_yaml}
                        </pre>
                    )}
                </>
            )}
        </DetailSection>
    );
}

// -----------------------------
// Subscriptions section
// -----------------------------
function SubscriptionsSection({ systemId }) {
    const [subs, setSubs] = useState(null);
    const [err, setErr] = useState(null);

    useEffect(() => {
        setSubs(null);
        setErr(null);
        fetchSystemSubscriptions(systemId).then(setSubs).catch((e) => setErr(e.message));
    }, [systemId]);

    return (
        <DetailSection title="Canon subscriptions">
            {err && <ErrorLine msg={err} />}
            {!err && !subs && <LoadingLine />}
            {subs && subs.subscriptions.length === 0 && (
                <div className="text-[12px] text-[var(--color-text-tertiary)] italic">
                    No canon store subscriptions (fail-closed).
                </div>
            )}
            {subs && subs.subscriptions.length > 0 && (
                <div className="border border-[var(--color-border-default)]">
                    {subs.subscriptions.map((sub) => (
                        <div
                            key={sub.store_id}
                            className="flex items-center gap-4 px-3 py-2 border-b border-[var(--color-border-default)] last:border-b-0"
                        >
                            <span className="font-mono text-[10px] w-16 text-[var(--color-text-tertiary)]">
                                rank {sub.precedence_rank}
                            </span>
                            <span className="font-mono text-[13px] text-[var(--color-text-primary)] w-32">
                                {sub.store_name}
                            </span>
                            <span className="text-[12px] text-[var(--color-text-secondary)] flex-1">
                                {sub.store_description || '—'}
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </DetailSection>
    );
}

// -----------------------------
// Canon lookups section
// -----------------------------
function CanonLookupsSection({ systemId }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);

    useEffect(() => {
        setData(null);
        setErr(null);
        fetchSystemCanonLookups(systemId, 30).then(setData).catch((e) => setErr(e.message));
    }, [systemId]);

    const histogram = data?.status_histogram || {};
    const totalShown = data?.count || 0;

    return (
        <DetailSection
            title="Recent Canon lookups"
            subtitle={totalShown > 0 ? `${totalShown} shown` : undefined}
        >
            {err && <ErrorLine msg={err} />}
            {!err && !data && <LoadingLine />}
            {data && totalShown === 0 && (
                <div className="text-[12px] text-[var(--color-text-tertiary)] italic">
                    No canon lookups recorded yet.
                </div>
            )}
            {data && totalShown > 0 && (
                <>
                    <div className="flex gap-4 mb-3">
                        {Object.entries(histogram).map(([status, count]) => (
                            <div key={status} className="flex items-center gap-1.5">
                                <StatusDot status={status} />
                                <span className="font-mono text-[11px] text-[var(--color-text-secondary)]">
                                    {status}: {count}
                                </span>
                            </div>
                        ))}
                    </div>
                    <div className="border border-[var(--color-border-default)] max-h-64 overflow-y-auto">
                        {data.lookups.map((lk) => (
                            <div
                                key={lk.id}
                                className="grid grid-cols-[140px_120px_1fr_100px] gap-2 px-3 py-1.5 border-b border-[var(--color-border-default)] last:border-b-0 items-center"
                            >
                                <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
                                    {lk.at?.slice(11, 19) || '—'}
                                </span>
                                <div className="flex items-center gap-1.5">
                                    <StatusDot status={lk.resolution_status} />
                                    <span className="font-mono text-[10px] text-[var(--color-text-secondary)]">
                                        {lk.resolution_status}
                                    </span>
                                </div>
                                <span className="font-mono text-[12px] text-[var(--color-text-body)] truncate">
                                    {lk.entity_requested}
                                </span>
                                <span className="font-mono text-[10px] text-[var(--color-text-tertiary)] truncate">
                                    {lk.resolved_from_store_name || '—'}
                                </span>
                            </div>
                        ))}
                    </div>
                </>
            )}
        </DetailSection>
    );
}

function StatusDot({ status }) {
    const color =
        status === 'declared' ? 'var(--color-ok)'
        : status === 'no_declaration' ? 'var(--color-sev-medium)'
        : status === 'disabled' ? 'var(--color-text-disabled)'
        : 'var(--color-sev-high)';
    return <span className="w-1.5 h-1.5" style={{ backgroundColor: color, borderRadius: '50%' }} />;
}

// -----------------------------
// Recent claims section
// -----------------------------
function RecentClaimsSection({ systemId }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);

    useEffect(() => {
        setData(null);
        setErr(null);
        fetchSystemRecentClaims(systemId, 15).then(setData).catch((e) => setErr(e.message));
    }, [systemId]);

    return (
        <DetailSection
            title="Recent claims"
            subtitle={data ? `${data.count} shown` : undefined}
        >
            {err && <ErrorLine msg={err} />}
            {!err && !data && <LoadingLine />}
            {data && data.count === 0 && (
                <div className="text-[12px] text-[var(--color-text-tertiary)] italic">
                    No claims from this system yet.
                </div>
            )}
            {data && data.count > 0 && (
                <div className="border border-[var(--color-border-default)] max-h-96 overflow-y-auto">
                    {data.claims.map((c) => (
                        <div
                            key={c.id}
                            className="px-3 py-2 border-b border-[var(--color-border-default)] last:border-b-0"
                        >
                            <div className="flex items-center gap-3 mb-1">
                                <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
                                    {c.extracted_at?.slice(0, 19).replace('T', ' ') || '—'}
                                </span>
                                <span className="font-mono text-[10px] px-1.5 py-0.5 bg-[var(--color-surface-2)] text-[var(--color-text-secondary)]">
                                    {c.entity_hint || '—'}
                                </span>
                                {c.is_historical && (
                                    <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
                                        historical
                                    </span>
                                )}
                            </div>
                            <div className="text-[12px] text-[var(--color-text-body)] leading-relaxed">
                                <span className="text-[var(--color-text-secondary)]">{c.subject}</span>
                                {' '}
                                <span className="text-[var(--color-text-tertiary)] italic">{c.predicate}</span>
                                {' '}
                                <span>{c.object}</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </DetailSection>
    );
}

// =====================================================
// shared primitives
// =====================================================
function DetailSection({ title, subtitle, children }) {
    return (
        <div className="px-6 py-5 border-b border-[var(--color-border-default)]">
            <div className="flex items-center gap-3 mb-3">
                <h2 className="text-[11px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)]">
                    {title}
                </h2>
                {subtitle && (
                    <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
                        {subtitle}
                    </span>
                )}
            </div>
            {children}
        </div>
    );
}

function FieldRow({ label, children }) {
    return (
        <div className="mb-3 last:mb-0">
            <div className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1">
                {label}
            </div>
            {children}
        </div>
    );
}

function LoadingLine() {
    return (
        <div className="text-[12px] text-[var(--color-text-tertiary)] font-mono italic">
            loading…
        </div>
    );
}

function ErrorLine({ msg }) {
    return (
        <div className="text-[12px] text-[var(--color-sev-critical)] font-mono">
            {msg}
        </div>
    );
}