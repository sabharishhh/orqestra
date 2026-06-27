import { useEffect } from 'react';
import { X, Target, FileText, FolderTree, ChevronRight } from 'lucide-react';

// =====================================================
// Recursive tree node — ASCII-style indented hierarchy
// =====================================================
function TreeNode({ node, isRoot = false, isLast = false, parentLines = [] }) {
  if (!node) return null;

  const decayLabel = node.depth_decay !== undefined && node.depth_decay < 1
    ? `×${node.depth_decay}`
    : null;

  const dollarColor = isRoot
    ? 'var(--color-sev-critical)'
    : 'var(--color-accent)';

  const Icon = isRoot ? FolderTree : FileText;
  const iconColor = isRoot ? 'var(--color-sev-critical)' : 'var(--color-text-tertiary)';

  const childrenCount = (node.children || []).length;

  return (
    <div className="font-mono text-[12px]">
      <div className="flex items-start gap-2 py-1.5 hover:bg-[var(--color-surface-2)] px-2 -mx-2 transition-colors">
        {/* Indentation guides */}
        <div className="flex shrink-0 pt-0.5">
          {parentLines.map((hasMore, i) => (
            <span key={i} className="w-4 text-[var(--color-text-disabled)] select-none">
              {hasMore ? '│' : ' '}
            </span>
          ))}
          {!isRoot && (
            <span className="w-4 text-[var(--color-text-disabled)] select-none">
              {isLast ? '└' : '├'}
            </span>
          )}
        </div>

        {/* Icon */}
        <Icon size={13} strokeWidth={1.5} style={{ color: iconColor }} className="shrink-0 mt-0.5" />

        {/* Content */}
        <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="font-semibold truncate"
                style={{ color: isRoot ? 'var(--color-text-primary)' : 'var(--color-text-body)' }}
              >
                {node.entity_hint || 'unknown'}
              </span>
              {isRoot && (
                <span
                  className="text-[10px] font-bold tracking-[0.05em] uppercase px-1.5 py-0.5 border"
                  style={{
                    color: 'var(--color-sev-critical)',
                    borderColor: 'var(--color-sev-critical)',
                    backgroundColor: 'color-mix(in srgb, var(--color-sev-critical) 15%, transparent)',
                  }}
                >
                  ROOT
                </span>
              )}
              {decayLabel && (
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 border"
                  style={{
                    color: 'var(--color-accent)',
                    borderColor: 'var(--color-accent)',
                    backgroundColor: 'color-mix(in srgb, var(--color-accent) 15%, transparent)',
                  }}
                >
                  {decayLabel}
                </span>
              )}
            </div>
            <div className="text-[11px] text-[var(--color-text-tertiary)] truncate mt-0.5">
              {node.system_name || '—'}
            </div>
          </div>

          <div className="shrink-0 font-bold tabular-nums" style={{ color: dollarColor }}>
            ${node.contribution?.toLocaleString() || '0'}
          </div>
        </div>
      </div>

      {childrenCount > 0 && (
        <div>
          {node.children.map((child, idx) => (
            <TreeNode
              key={child.claim_id || idx}
              node={child}
              isRoot={false}
              isLast={idx === childrenCount - 1}
              parentLines={[...parentLines, !isLast]}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// =====================================================
// Side label (A / B header for each tree)
// =====================================================
function SideLabel({ side, totalUsd }) {
  return (
    <div className="flex items-center justify-between py-2 px-3 mt-4 mb-1 bg-[var(--color-surface-2)] border-l-2 border-[var(--color-accent)]">
      <span className="text-[11px] font-bold text-[var(--color-text-secondary)] tracking-[0.05em] uppercase">
        Side {side}
      </span>
      <span className="text-[13px] font-bold font-mono tabular-nums" style={{ color: 'var(--color-accent)' }}>
        ${totalUsd?.toLocaleString() || '0'}
      </span>
    </div>
  );
}

// =====================================================
// Main slide-over panel
// =====================================================
export default function BlastRadiusPanel({ data, contradiction, onClose }) {
  // ESC to close
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const isOpen = !!data && !!contradiction;
  const idShort = data?.contradiction_id?.slice(0, 8).toUpperCase();
  const hasDescendants = (data?.descendant_count || 0) > 0;
  const propagationMultiplier = data?.root_cost_usd > 0
    ? (data.blast_radius_usd / data.root_cost_usd).toFixed(1)
    : '1.0';

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={`fixed inset-0 bg-black/40 backdrop-blur-[2px] z-40 transition-opacity duration-200 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
      />

      {/* Slide-over panel */}
      <aside
        className={`fixed top-0 right-0 h-screen w-[480px] bg-[var(--color-surface-1)] border-l border-[var(--color-border-default)] z-50 flex flex-col transition-transform duration-200 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {data && (
          <>
            {/* Header */}
            <div className="px-5 py-4 border-b border-[var(--color-border-default)] bg-[var(--color-surface-2)]">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <Target size={16} strokeWidth={1.5} style={{ color: 'var(--color-sev-critical)' }} className="shrink-0" />
                  <h2 className="text-[15px] font-semibold text-[var(--color-text-primary)] truncate">
                    Blast-Radius Impact
                  </h2>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[11px] font-mono text-[var(--color-text-tertiary)] bg-[var(--color-surface-0)] border border-[var(--color-border-default)] px-2 py-1">
                    #{idShort}
                  </span>
                  <button
                    onClick={onClose}
                    className="p-1 hover:bg-[var(--color-surface-3)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
                    aria-label="Close panel"
                  >
                    <X size={16} strokeWidth={1.5} />
                  </button>
                </div>
              </div>
              <p className="text-[12px] text-[var(--color-text-tertiary)] leading-[18px] mt-2">
                Estimated dollar exposure across descendant claims, decayed by depth from the root contradiction.
              </p>
            </div>

            {/* Top-line numbers */}
            <div className="px-5 py-4 border-b border-[var(--color-border-default)] grid grid-cols-2 gap-4">
              <div>
                <div className="text-[10px] font-bold text-[var(--color-text-tertiary)] uppercase tracking-[0.05em] mb-1">
                  Root cost
                </div>
                <div className="text-[20px] font-bold text-[var(--color-text-primary)] font-mono tabular-nums">
                  ${data.root_cost_usd?.toLocaleString() || '0'}
                </div>
              </div>
              <div>
                <div className="text-[10px] font-bold text-[var(--color-text-tertiary)] uppercase tracking-[0.05em] mb-1">
                  Propagation
                </div>
                <div className="text-[20px] font-bold font-mono tabular-nums flex items-baseline gap-2" style={{ color: 'var(--color-accent)' }}>
                  {propagationMultiplier}×
                  <span className="text-[11px] text-[var(--color-text-tertiary)] font-normal">
                    decay {data.decay_factor}
                  </span>
                </div>
              </div>
            </div>

            {/* Tree */}
            <div className="flex-1 overflow-y-auto px-4 py-3">
              {!hasDescendants ? (
                <div className="text-center text-[var(--color-text-tertiary)] text-[12px] font-mono py-12">
                  <ChevronRight size={20} strokeWidth={1.5} className="mx-auto mb-2 opacity-40" />
                  <div>Single-event exposure.</div>
                  <div className="text-[var(--color-text-disabled)]">No descendant claims propagate this contradiction yet.</div>
                </div>
              ) : (
                <>
                  {data.side_a?.tree && (
                    <>
                      <SideLabel side="A" totalUsd={data.side_a.total_usd} />
                      <TreeNode node={data.side_a.tree} isRoot={true} isLast={true} parentLines={[]} />
                    </>
                  )}
                  {data.side_b?.tree && (
                    <>
                      <SideLabel side="B" totalUsd={data.side_b.total_usd} />
                      <TreeNode node={data.side_b.tree} isRoot={true} isLast={true} parentLines={[]} />
                    </>
                  )}
                </>
              )}
            </div>

            {/* Footer — Total Exposure */}
            <div className="px-5 py-4 border-t border-[var(--color-border-strong)] bg-[var(--color-surface-2)]">
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-[10px] font-bold text-[var(--color-text-tertiary)] uppercase tracking-[0.05em] mb-0.5">
                    Total Exposure
                  </div>
                  <div className="text-[11px] text-[var(--color-text-tertiary)] font-mono">
                    {data.descendant_count} descendant{data.descendant_count === 1 ? '' : 's'}
                  </div>
                </div>
                <div className="text-[28px] font-bold font-mono tabular-nums" style={{ color: 'var(--color-sev-critical)' }}>
                  ${data.blast_radius_usd?.toLocaleString() || '0'}
                </div>
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  );
}