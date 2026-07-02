import { useEffect, useState } from 'react';
import { fetchROI, fetchCanonList, fetchCanonLookupSummary } from '../api';

export default function EstateScoreHeader() {
    const [roi, setRoi] = useState(null);
    const [canonHealth, setCanonHealth] = useState(null); // {declared, total}
    const [lookupSummary, setLookupSummary] = useState(null);

    useEffect(() => {
        const load = () => {
            fetchROI().then(setRoi).catch(console.error);
            fetchCanonList(true).then((j) => {
                // include_empty=true so we count undeclared entities in the denominator
                const totalDeclared = j.declared?.length || 0;
                const totalCandidates = j.candidates?.length || 0;
                setCanonHealth({ declared: totalDeclared, total: totalCandidates });
            }).catch(console.error);
            fetchCanonLookupSummary().then(setLookupSummary).catch(console.error);
        };
        load();
        const t = setInterval(load, 10000);
        return () => clearInterval(t);
    }, []);

    if (!roi) return <SkeletonHeader />;

    return (
        <div className="grid grid-cols-6 border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
            <StatTile
                label="Active contradictions"
                value={roi.active_contradictions}
            />
            <StatTile
                label="Critical / High"
                value={
                    <>
                        <span style={{ color: 'var(--color-sev-critical)' }}>
                            {roi.severity_breakdown.critical}
                        </span>
                        <span className="text-[var(--color-text-tertiary)] mx-1">/</span>
                        <span style={{ color: 'var(--color-sev-high)' }}>
                            {roi.severity_breakdown.high}
                        </span>
                    </>
                }
            />
            <StatTile
                label="Financial exposure"
                value={`$${roi.total_financial_exposure_usd.toLocaleString()}`}
            />
            <StatTile
                label="Canon declared"
                value={
                    canonHealth
                        ? <CanonRatio declared={canonHealth.declared} total={canonHealth.total} />
                        : '—'
                }
            />
            <StatTile
                label="Canon lookups / hr"
                value={
                    lookupSummary
                        ? <LookupCount summary={lookupSummary} />
                        : '—'
                }
            />
            <StatTile
                label="Status"
                small
                value={
                    <span className="inline-flex items-center gap-2 text-[var(--color-text-body)]">
                        <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-ok)]" />
                        <span className="font-mono text-[13px]">Live</span>
                    </span>
                }
            />
        </div>
    );
}

function CanonRatio({ declared, total }) {
    if (total === 0) {
        return <span className="text-[var(--color-text-tertiary)]">0 / 0</span>;
    }
    const pct = declared / total;
    const color = pct >= 0.8 ? 'var(--color-ok)'
        : pct >= 0.5 ? 'var(--color-sev-medium)'
        : 'var(--color-sev-high)';
    return (
        <span style={{ color }}>
            {declared}
            <span className="text-[var(--color-text-tertiary)] mx-1">/</span>
            <span className="text-[var(--color-text-secondary)]">{total}</span>
        </span>
    );
}

function LookupCount({ summary }) {
    const declared = summary.last_hour_by_status?.declared ?? 0;
    const missed = summary.last_hour_by_status?.no_declaration ?? 0;
    return (
        <span>
            {summary.last_hour}
            {summary.last_hour > 0 && (
                <span className="ml-2 font-mono text-[11px] text-[var(--color-text-tertiary)]">
                    ({declared}✓ {missed}∅)
                </span>
            )}
        </span>
    );
}

function SkeletonHeader() {
    return (
        <div className="grid grid-cols-6 border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
            {[0, 1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="px-6 py-4 border-r border-[var(--color-border-default)] last:border-r-0">
                    <div className="h-3 w-20 bg-[var(--color-surface-2)] animate-pulse mb-2" />
                    <div className="h-6 w-16 bg-[var(--color-surface-2)] animate-pulse" />
                </div>
            ))}
        </div>
    );
}

function StatTile({ label, value, small }) {
    return (
        <div className="px-6 py-4 border-r border-[var(--color-border-default)] last:border-r-0">
            <div className="text-[11px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1.5">
                {label}
            </div>
            <div className={`font-mono font-medium text-[var(--color-text-primary)] ${small ? 'text-[16px]' : 'text-[24px]'} leading-none`}>
                {value}
            </div>
        </div>
    );
}