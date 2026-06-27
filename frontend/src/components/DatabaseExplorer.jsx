import { useState, useEffect } from 'react';
import { Database, ChevronDown } from 'lucide-react';

const TABLES = ['systems', 'entities', 'claims', 'contradictions', 'resolution_proposals', 'coherence_scores', 'contrastive_feedback'];

export default function DatabaseExplorer() {
  const [table, setTable] = useState('systems');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);

  useEffect(() => {
    setLoading(true);
    setExpandedRow(null);
    fetch(`http://localhost:8000/admin/table/${table}`)
      .then(res => res.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [table]);

  const columns = data[0] ? Object.keys(data[0]) : [];

  return (
    <div className="flex h-screen">
      <aside className="w-56 shrink-0 bg-[var(--color-surface-1)] border-r border-[var(--color-border-default)] flex flex-col">
        <div className="h-14 px-4 flex items-center border-b border-[var(--color-border-default)]">
          <Database size={14} strokeWidth={1.5} className="text-[var(--color-text-secondary)] mr-2" />
          <span className="text-[11px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)]">Tables</span>
        </div>
        <nav className="flex-1 py-2 overflow-auto">
          {TABLES.map(t => (
            <button
              key={t}
              onClick={() => setTable(t)}
              className={`w-full text-left h-9 px-4 font-mono text-[13px] transition-colors relative ${
                table === t
                  ? 'bg-[var(--color-surface-2)] text-[var(--color-text-primary)] before:absolute before:left-0 before:top-0 before:h-full before:w-[2px] before:bg-[var(--color-accent)]'
                  : 'text-[var(--color-text-body)] hover:bg-[var(--color-surface-2)]'
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </aside>

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 px-6 flex items-center justify-between border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-[16px] font-medium text-[var(--color-text-primary)]">{table}</h1>
            <span className="font-mono text-[11px] text-[var(--color-text-tertiary)] uppercase tracking-[0.05em]">
              {data.length} rows
            </span>
          </div>
        </header>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="p-6 font-mono text-[12px] text-[var(--color-text-secondary)] animate-pulse">Loading {table}…</div>
          ) : data.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center">
              <Database size={20} strokeWidth={1.5} className="text-[var(--color-text-disabled)] mb-3" />
              <div className="text-[14px] font-medium text-[var(--color-text-body)] mb-1">No rows.</div>
              <div className="text-[12px] text-[var(--color-text-secondary)] font-mono">{table} is empty.</div>
            </div>
          ) : (
            <table className="w-full text-left">
              <thead className="sticky top-0 bg-[var(--color-surface-2)] border-b border-[var(--color-border-default)]">
                <tr>
                  <th className="w-8" />
                  {columns.map(k => (
                    <th key={k} className="px-3 py-2.5 text-[11px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] font-mono">
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => {
                  const isExpanded = expandedRow === i;
                  return (
                    <Fragment key={i}>
                      <tr
                        onClick={() => setExpandedRow(isExpanded ? null : i)}
                        className={`border-b border-[var(--color-border-default)] cursor-pointer transition-colors ${
                          isExpanded ? 'bg-[var(--color-surface-2)]' : 'hover:bg-[var(--color-surface-2)]'
                        }`}
                      >
                        <td className="px-2 py-2 align-top">
                          <ChevronDown size={14} strokeWidth={1.5}
                            className={`text-[var(--color-text-tertiary)] transition-transform ${isExpanded ? '' : '-rotate-90'}`} />
                        </td>
                        {columns.map(k => (
                          <td key={k} className="px-3 py-2 font-mono text-[12px] text-[var(--color-text-body)] truncate max-w-[240px]">
                            {formatCell(row[k])}
                          </td>
                        ))}
                      </tr>
                      {isExpanded && (
                        <tr className="bg-[var(--color-surface-1)] border-b border-[var(--color-border-default)]">
                          <td colSpan={columns.length + 1} className="px-6 py-4">
                            <pre className="font-mono text-[11px] text-[var(--color-text-body)] bg-[var(--color-surface-0)] border border-[var(--color-border-default)] p-3 overflow-x-auto leading-[16px]">
                              {JSON.stringify(row, null, 2)}
                            </pre>
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
    </div>
  );
}

function formatCell(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v);
}

import { Fragment } from 'react';