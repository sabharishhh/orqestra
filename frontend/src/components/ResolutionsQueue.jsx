import { useState, useEffect } from 'react';
import { Check, X, AlertTriangle, ExternalLink, Inbox } from 'lucide-react';

const API_KEY = "oq-dev-test-key-replace-in-production";
const API_BASE = "http://localhost:8000";

export default function ResolutionsQueue() {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchProposals = async () => {
    try {
      const res = await fetch(`${API_BASE}/resolutions/pending`, {
        headers: { Authorization: `Bearer ${API_KEY}` },
      });
      const data = await res.json();
      setProposals(data.slice(0, 5));
    } catch (err) {
      console.error('Failed to fetch proposals', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchProposals(); }, []);

  const handleFeedback = async (id, action) => {
    setProposals(prev => prev.filter(p => p.id !== id));
    try {
      await fetch(`${API_BASE}/resolutions/${id}/feedback`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ action }),
      });
    } catch (err) {
      console.error('Feedback submission failed', err);
      fetchProposals();
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <header className="h-14 px-6 flex items-center justify-between border-b border-[var(--color-border-default)] bg-[var(--color-surface-1)]">
        <div>
          <h1 className="text-[18px] font-semibold text-[var(--color-text-primary)] tracking-[-0.01em]">
            Resolution Queue
          </h1>
        </div>
        <span className="font-mono text-[13px] text-[var(--color-text-secondary)]">
          {proposals.length} / 5 pending
        </span>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="font-mono text-[12px] text-[var(--color-text-secondary)] animate-pulse">
            Loading queue…
          </div>
        ) : proposals.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="max-w-4xl mx-auto space-y-4">
            {proposals.map(p => (
              <ProposalCard
                key={p.id}
                proposal={p}
                onAccept={() => handleFeedback(p.id, 'accept')}
                onReject={() => handleFeedback(p.id, 'reject')}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ProposalCard({ proposal, onAccept, onReject }) {
  return (
    <div className="bg-[var(--color-surface-1)] border border-[var(--color-border-default)] p-5">
      <div className="flex justify-between items-start mb-4">
        <span
          className="inline-flex items-center gap-1.5 font-mono text-[11px] font-medium tracking-[0.02em] px-2 py-0.5 border"
          style={{
            color: 'var(--color-sev-medium)',
            borderColor: 'var(--color-sev-medium)',
            backgroundColor: 'color-mix(in srgb, var(--color-sev-medium) 15%, transparent)',
          }}
        >
          <AlertTriangle size={11} strokeWidth={1.5} />
          {proposal.estimated_cost} exposure
        </span>
        <a
          href={proposal.target_uri}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-[12px] font-medium text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] transition-colors"
        >
          View source policy <ExternalLink size={12} strokeWidth={1.5} />
        </a>
      </div>

      <div className="mb-4">
        <SectionLabel>Diagnosis</SectionLabel>
        <p className="text-[14px] text-[var(--color-text-body)] leading-[20px]">
          {proposal.why_they_contradict}
        </p>
      </div>

      <div className="bg-[var(--color-surface-0)] border border-[var(--color-border-default)] p-3 mb-5">
        <SectionLabel>Recommended action</SectionLabel>
        <p className="text-[13px] text-[var(--color-text-body)] leading-[20px]">
          {proposal.recommended_action}
        </p>
      </div>

      <div className="flex gap-2 pt-4 border-t border-[var(--color-border-default)]">
        <button
          onClick={onAccept}
          className="flex-1 inline-flex items-center justify-center gap-2 h-9 bg-[var(--color-accent)] text-[var(--color-surface-0)] text-[13px] font-medium hover:bg-[var(--color-accent-hover)] transition-colors"
        >
          <Check size={14} strokeWidth={1.5} /> Approve & deploy
        </button>
        <button
          onClick={onReject}
          className="flex-1 inline-flex items-center justify-center gap-2 h-9 bg-[var(--color-surface-2)] text-[var(--color-text-body)] text-[13px] font-medium border border-[var(--color-border-strong)] hover:bg-[var(--color-surface-3)] transition-colors"
        >
          <X size={14} strokeWidth={1.5} /> Reject
        </button>
      </div>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="text-[11px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)] mb-1.5">
      {children}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center">
      <Inbox size={20} strokeWidth={1.5} className="text-[var(--color-text-disabled)] mb-3" />
      <div className="text-[14px] font-medium text-[var(--color-text-body)] mb-1">
        Queue clear.
      </div>
      <div className="text-[12px] text-[var(--color-text-secondary)]">
        0 pending resolutions.
      </div>
    </div>
  );
}