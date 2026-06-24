import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, ExternalLink } from 'lucide-react';

const API_KEY = "oq-dev-test-key-replace-in-production"; // Update with your actual auth strategy

export default function ResolutionsQueue() {
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchProposals = async () => {
    try {
      const res = await fetch('http://localhost:8000/resolutions/pending', {
        headers: { 'Authorization': `Bearer ${API_KEY}` }
      });
      const data = await res.json();
      // F8.3 Compliance: Strict hard-cap to prevent review fatigue
      setProposals(data.slice(0, 5)); 
    } catch (err) {
      console.error("Failed to fetch proposals", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProposals();
  }, []);

  const handleFeedback = async (id, action) => {
    // Optimistic UI update
    setProposals(prev => prev.filter(p => p.id !== id));
    
    try {
      await fetch(`http://localhost:8000/resolutions/${id}/feedback`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ action }) // "accept" or "reject"
      });
      // This hits the backend and triggers record_feedback Celery task!
    } catch (err) {
      console.error("Feedback submission failed", err);
      fetchProposals(); // Revert on failure
    }
  };

  if (loading) return <div className="text-slate-400">Loading resolution queue...</div>;
  if (proposals.length === 0) return <div className="text-slate-500">Inbox zero. No pending resolutions.</div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Resolution Queue</h1>
          <p className="text-slate-400 text-sm">Review LLM-generated fixes to fine-tune the detection engine.</p>
        </div>
        <div className="bg-slate-800 px-3 py-1 rounded-full text-xs font-medium text-slate-300">
          {proposals.length} / 5 Pending
        </div>
      </div>

      {proposals.map(proposal => (
        <div key={proposal.id} className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-amber-500 bg-amber-500/10 px-3 py-1 rounded-md text-sm font-semibold">
              <AlertTriangle size={16} />
              {proposal.estimated_cost} Exposure
            </div>
            <a href={proposal.target_uri} target="_blank" rel="noreferrer" className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-sm font-medium transition-colors">
              View Source Policy <ExternalLink size={14} />
            </a>
          </div>

          <p className="text-lg text-slate-200 font-medium mb-4 leading-relaxed">
            {proposal.why_they_contradict}
          </p>

          <div className="bg-slate-950 rounded-lg p-4 mb-6 border border-slate-800/50">
            <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Recommended Action</h4>
            <p className="text-slate-300">{proposal.recommended_action}</p>
          </div>

          <div className="flex gap-4 border-t border-slate-800 pt-6">
            <button 
              onClick={() => handleFeedback(proposal.id, 'accept')}
              className="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-medium py-2.5 rounded-lg transition-colors flex justify-center items-center gap-2"
            >
              <CheckCircle size={18} /> Approve & Deploy Fix
            </button>
            <button 
              onClick={() => handleFeedback(proposal.id, 'reject')}
              className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium py-2.5 rounded-lg transition-colors flex justify-center items-center gap-2 border border-slate-700"
            >
              <XCircle size={18} /> Reject (Trains Model)
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}