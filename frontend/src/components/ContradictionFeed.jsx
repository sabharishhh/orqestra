import { useEffect, useState } from 'react';
import { fetchContradictions, fetchResolution } from '../api';

export default function ContradictionFeed() {
    const [conflicts, setConflicts] = useState([]);
    const [resolutions, setResolutions] = useState({});
    const [loadingId, setLoadingId] = useState(null);

    useEffect(() => {
        fetchContradictions().then(setConflicts).catch(console.error);
        const interval = setInterval(() => fetchContradictions().then(setConflicts).catch(console.error), 5000);
        return () => clearInterval(interval);
    }, []);

    const loadResolution = async (id) => {
        setLoadingId(id);
        try {
            const res = await fetchResolution(id);
            setResolutions(prev => ({ ...prev, [id]: res }));
        } catch (e) {
            console.error("Resolution not ready yet", e);
            alert("Resolution agent is still processing this conflict.");
        }
        setLoadingId(null);
    };

    const getSeverityColor = (sev) => {
        const map = { 
            critical: 'bg-red-500/10 text-red-400 border-red-500/30 border-t-red-500', 
            high: 'bg-orange-500/10 text-orange-400 border-orange-500/30 border-t-orange-500', 
            medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30 border-t-yellow-500' 
        };
        return map[sev] || 'bg-green-500/10 text-green-400 border-green-500/30 border-t-green-500';
    };

    return (
        <div className="space-y-6">
            <h2 className="text-2xl font-bold text-white mb-6">Live Knowledge Collisions</h2>
            {conflicts.length === 0 && <div className="text-slate-400">No active contradictions. Estate is coherent.</div>}
            
            {conflicts.map(c => {
                const colors = getSeverityColor(c.severity);
                return (
                <div key={c.id} className={`bg-slate-900 border rounded-xl shadow-lg border-t-4 ${colors.split(' ')[3]} border-slate-800 transition-all duration-300`}>
                    <div className={`px-6 py-4 border-b border-slate-800 flex justify-between items-center ${colors.split(' ')[0]}`}>
                        <span className={`font-bold uppercase tracking-wide text-sm flex items-center gap-2 ${colors.split(' ')[1]}`}>
                            ⚠️ [{c.severity}] Collision: {c.entity_hint}
                        </span>
                        <span className="text-sm font-mono text-slate-400">Confidence: {(c.nli_score * 100).toFixed(1)}%</span>
                    </div>
                    
                    <div className="p-6">
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                                <div className="text-xs text-slate-500 uppercase font-bold mb-2 tracking-wider">🖥️ {c.system_a.name} Asserted:</div>
                                <div className="font-mono text-sm text-slate-300 leading-relaxed">"{c.system_a.claim}"</div>
                            </div>
                            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                                <div className="text-xs text-slate-500 uppercase font-bold mb-2 tracking-wider">🖥️ {c.system_b.name} Asserted:</div>
                                <div className="font-mono text-sm text-slate-300 leading-relaxed">"{c.system_b.claim}"</div>
                            </div>
                        </div>

                        {!resolutions[c.id] ? (
                            <button 
                                onClick={() => loadResolution(c.id)}
                                disabled={loadingId === c.id}
                                className="bg-blue-600/20 hover:bg-blue-600/40 border border-blue-500/50 text-blue-400 px-5 py-2 rounded-lg font-medium text-sm transition-all disabled:opacity-50"
                            >
                                {loadingId === c.id ? 'Fetching Analysis...' : 'View Resolution Proposal'}
                            </button>
                        ) : (
                            <div className="mt-6 pt-6 border-t border-slate-800 space-y-5 animate-in fade-in slide-in-from-top-4">
                                <div>
                                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Analytical Diagnosis</h4>
                                    <p className="text-slate-300">{resolutions[c.id].why_they_contradict}</p>
                                </div>
                                <div>
                                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Business Risk</h4>
                                    <p className="text-red-400 font-medium">{resolutions[c.id].risk_reason}</p>
                                </div>
                                <div className="bg-green-950/30 border border-green-500/20 p-5 rounded-xl">
                                    <h4 className="text-xs font-bold text-green-500 uppercase tracking-wider mb-2">🛠️ Enforced Remediation Target</h4>
                                    <p className="text-green-400 font-medium mb-3">{resolutions[c.id].recommended_action}</p>
                                    <code className="text-xs bg-black/50 border border-green-500/20 px-3 py-1.5 rounded text-green-300 font-mono">
                                        Target URI: {resolutions[c.id].target_uri}
                                    </code>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )})}
        </div>
    );
}