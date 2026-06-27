import { useEffect, useState } from 'react';
import { fetchROI } from '../api';

export default function EstateScoreHeader() {
  const [roi, setRoi] = useState(null);

  useEffect(() => {
    fetchROI().then(setRoi).catch(console.error);
    const t = setInterval(() => fetchROI().then(setRoi).catch(console.error), 5000);
    return () => clearInterval(t);
  }, []);

  if (!roi) {
    return (
      <div className="grid grid-cols-4 border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="px-6 py-4 border-r border-[var(--color-border-default)] last:border-r-0">
            <div className="h-3 w-20 bg-[var(--color-surface-2)] animate-pulse mb-2" />
            <div className="h-6 w-16 bg-[var(--color-surface-2)] animate-pulse" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-4 border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
      <StatTile label="Active contradictions" value={roi.active_contradictions} />
      <StatTile
        label="Critical / High"
        value={
          <>
            <span style={{ color: 'var(--color-sev-critical)' }}>{roi.severity_breakdown.critical}</span>
            <span className="text-[var(--color-text-tertiary)] mx-1">/</span>
            <span style={{ color: 'var(--color-sev-high)' }}>{roi.severity_breakdown.high}</span>
          </>
        }
      />
      <StatTile label="Financial exposure" value={`$${roi.total_financial_exposure_usd.toLocaleString()}`} />
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