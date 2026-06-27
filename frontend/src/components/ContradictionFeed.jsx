import { useEffect, useState, Fragment } from 'react';
import { fetchContradictions, fetchResolution } from '../api';
import ContradictionLineageTree from './ContradictionLineageTree';
import { Network, Wand2, Check, ChevronRight, Inbox } from 'lucide-react';
import EstateScoreHeader from './EstateScoreHeader';

const SEV_STYLES = {
  critical: { fg: 'var(--color-sev-critical)', label: 'CRITICAL' },
  high:     { fg: 'var(--color-sev-high)',     label: 'HIGH' },
  medium:   { fg: 'var(--color-sev-medium)',   label: 'MEDIUM' },
  low:      { fg: 'var(--color-sev-low)',      label: 'LOW' },
};

function SeverityTag({ severity }) {
  const sev = SEV_STYLES[severity] || SEV_STYLES.low;
  return (
    <span
      className="inline-flex items-center font-mono text-[11px] font-medium tracking-[0.02em] px-1.5 py-0.5 border"
      style={{
        color: sev.fg,
        borderColor: sev.fg,
        backgroundColor: `color-mix(in srgb, ${sev.fg} 15%, transparent)`,
      }}
    >
      {sev.label}
    </span>
  );
}

export default function ContradictionFeed() {
  const [conflicts, setConflicts] = useState([]);
  const [resolutions, setResolutions] = useState({});
  const [loadingId, setLoadingId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [lineageId, setLineageId] = useState(null);

  useEffect(() => {
    fetchContradictions().then(setConflicts).catch(console.error);
    const t = setInterval(() => fetchContradictions().then(setConflicts).catch(console.error), 5000);
    return () => clearInterval(t);
  }, []);

  const loadResolution = async (id, e) => {
    e?.stopPropagation();
    setLoadingId(id);
    try {
      const res = await fetchResolution(id);
      setResolutions(prev => ({ ...prev, [id]: res }));
    } catch (err) {
      console.error(err);
    }
    setLoadingId(null);
  };

  const toggleExpand = (id) => setExpandedId(expandedId === id ? null : id);
  const toggleLineage = (id, e) => {
    e?.stopPropagation();
    setLineageId(lineageId === id ? null : id);
  };

  return (
    <div className="flex flex-col h-screen">
      {/* Page header */}
      <header className="h-14 px-6 flex items-center justify-between border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
        <h1 className="text-[18px] font-semibold text-[var(--color-text-primary)] tracking-[-0.01em]">
          Contradiction Feed
        </h1>
        <span className="font-mono text-[13px] text-[var(--color-text-secondary)]">
          {conflicts.length} contradiction{conflicts.length === 1 ? '' : 's'}
        </span>
      </header>

      {/* Stat strip */}
      <EstateScoreHeader />

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {conflicts.length === 0 ? (
          <EmptyState />
        ) : (
          <table className="w-full text-left">
            <thead className="sticky top-0 bg-[var(--color-surface-2)] border-b border-[var(--color-border-default)]">
              <tr className="text-[11px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)]">
                <th className="px-3 py-2.5 w-[100px]">Sev</th>
                <th className="px-3 py-2.5">Entity</th>
                <th className="px-3 py-2.5">Systems</th>
                <th className="px-3 py-2.5 text-right w-[100px]">Conf</th>
                <th className="px-3 py-2.5 w-[120px]">Actions</th>
              </tr>
            </thead>
            <tbody>
              {conflicts.map(c => {
                const isExpanded = expandedId === c.id;
                const isLineage = lineageId === c.id;
                const res = resolutions[c.id];
                return (
                  <Fragment key={c.id}>
                    <tr
                      onClick={() => toggleExpand(c.id)}
                      className={`border-b border-[var(--color-border-default)] cursor-pointer transition-colors ${
                        isExpanded ? 'bg-[var(--color-surface-2)]' : 'hover:bg-[var(--color-surface-2)]'
                      }`}
                    >
                      <td className="px-3 py-2.5">
                        <SeverityTag severity={c.severity} />
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[13px] text-[var(--color-text-primary)]">
                        {c.entity_hint}
                      </td>
                      <td className="px-3 py-2.5 text-[13px] text-[var(--color-text-secondary)]">
                        <span className="font-mono text-[var(--color-accent)]">{c.system_a.name}</span>
                        <span className="text-[var(--color-text-tertiary)] mx-2">vs</span>
                        <span className="font-mono text-[var(--color-accent)]">{c.system_b.name}</span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-[13px] text-[var(--color-text-body)]">
                        {(c.nli_score * 100).toFixed(0)}%
                      </td>
                      <td className="px-3 py-2.5">
                        <ChevronRight
                          size={16}
                          strokeWidth={1.5}
                          className={`text-[var(--color-text-tertiary)] transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                        />
                      </td>
                    </tr>

                    {/* Expanded detail */}
                    {isExpanded && (
                      <tr className="bg-[var(--color-surface-1)] border-b border-[var(--color-border-default)]">
                        <td colSpan={5} className="px-6 py-5">
                          <div className="grid grid-cols-2 gap-4 mb-4">
                            <ClaimCard system={c.system_a} />
                            <ClaimCard system={c.system_b} />
                          </div>

                          {/* Action row */}
                          <div className="flex gap-2 mb-4">
                            {!res ? (
                              <button
                                onClick={(e) => loadResolution(c.id, e)}
                                disabled={loadingId === c.id}
                                className="inline-flex items-center gap-2 h-8 px-3 bg-[var(--color-accent)] text-[var(--color-surface-0)] text-[13px] font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
                              >
                                <Wand2 size={14} strokeWidth={1.5} />
                                {loadingId === c.id ? 'Analyzing…' : 'Generate resolution'}
                              </button>
                            ) : (
                              <span
                                className="inline-flex items-center gap-2 h-8 px-3 text-[13px] font-medium border"
                                style={{
                                  color: 'var(--color-ok)',
                                  borderColor: 'var(--color-ok)',
                                  backgroundColor: 'color-mix(in srgb, var(--color-ok) 15%, transparent)',
                                }}
                              >
                                <Check size={14} strokeWidth={1.5} />
                                Resolution generated
                              </span>
                            )}
                            <button
                              onClick={(e) => toggleLineage(c.id, e)}
                              className={`inline-flex items-center gap-2 h-8 px-3 text-[13px] font-medium border border-[var(--color-border-strong)] transition-colors ${
                                isLineage
                                  ? 'bg-[var(--color-surface-3)] text-[var(--color-text-primary)]'
                                  : 'bg-[var(--color-surface-2)] text-[var(--color-text-body)] hover:bg-[var(--color-surface-3)]'
                              }`}
                            >
                              <Network size={14} strokeWidth={1.5} />
                              {isLineage ? 'Hide lineage' : 'View lineage'}
                            </button>
                          </div>

                          {/* Resolution detail */}
                          {res && <ResolutionPanel res={res} />}

                          {/* Lineage tree */}
                          {isLineage && (
                            <div className="mt-4 pt-4 border-t border-[var(--color-border-default)]">
                              <ContradictionLineageTree conflict={c} />
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ClaimCard({ system }) {
  return (
    <div className="bg-[var(--color-surface-2)] border border-[var(--color-border-default)] p-3">
      <div className="font-mono text-[11px] text-[var(--color-accent)] mb-2">
        {system.name}
      </div>
      <div className="text-[13px] text-[var(--color-text-body)] leading-[20px]">
        {system.claim}
      </div>
    </div>
  );
}

function ResolutionPanel({ res }) {
  return (
    <div className="grid grid-cols-3 gap-4 pt-4 border-t border-[var(--color-border-default)]">
      <Section label="Diagnosis" body={res.why_they_contradict} />
      <Section label="Business risk" body={res.risk_reason} color="var(--color-sev-critical)" />
      <div>
        <SectionLabel color="var(--color-ok)">Remediation</SectionLabel>
        <p className="text-[13px] text-[var(--color-text-body)] leading-[20px] mb-2">
          {res.recommended_action}
        </p>
        <code className="block font-mono text-[11px] text-[var(--color-ok)] bg-[var(--color-surface-0)] border border-[var(--color-border-default)] px-2 py-1.5 overflow-x-auto">
          {res.target_uri}
        </code>
      </div>
    </div>
  );
}

function Section({ label, body, color }) {
  return (
    <div>
      <SectionLabel color={color}>{label}</SectionLabel>
      <p className="text-[13px] text-[var(--color-text-body)] leading-[20px]">{body}</p>
    </div>
  );
}

function SectionLabel({ children, color }) {
  return (
    <div
      className="text-[11px] font-bold tracking-[0.05em] uppercase mb-1.5"
      style={{ color: color || 'var(--color-text-tertiary)' }}
    >
      {children}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center">
      <Inbox size={20} strokeWidth={1.5} className="text-[var(--color-text-disabled)] mb-3" />
      <div className="text-[14px] font-medium text-[var(--color-text-body)] mb-1">
        No contradictions detected.
      </div>
      <div className="text-[12px] text-[var(--color-text-secondary)]">
        Your AI estate is coherent.
      </div>
    </div>
  );
}