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
            critical: 'bg-red-500/10 text-red-400 border-red-500/30 border-l-red-500', 
            high: 'bg-orange-500/10 text-orange-400 border-orange-500/30 border-l-orange-500', 
            medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30 border-l-yellow-500' 
        };
        return map[sev] || 'bg-green-500/10 text-green-400 border-green-500/30 border-l-green-500';
    };

    return (
        <div className="bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl h-[600px] flex flex-col overflow-hidden">
            
            {/* Sidebar Header */}
            <div className="px-5 py-4 border-b border-slate-800/80 flex items-center justify-between bg-slate-900/50">
                <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300 flex items-center gap-3">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                    </span>
                    Live Collision Feed
                </h2>
                <span className="bg-slate-800 border border-slate-700 text-[10px] uppercase font-mono px-2 py-1 rounded text-slate-400">
                    {conflicts.length} Active
                </span>
            </div>
            
            {/* Scrollable Container (Custom Webkit Scrollbar styling) */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-700 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-transparent">
                
                {conflicts.length === 0 && (
                    <div className="text-center mt-10 text-slate-500 text-sm font-mono">
                        Estate is currently coherent.
                    </div>
                )}
                
                {conflicts.map(c => {
                    const colors = getSeverityColor(c.severity);
                    return (
                    <div key={c.id} className={`bg-slate-900 border rounded-xl shadow-lg border-l-4 ${colors.split(' ')[3]} border-slate-800 transition-all duration-300`}>
                        <div className={`px-4 py-3 border-b border-slate-800/50 flex justify-between items-center ${colors.split(' ')[0]}`}>
                            <span className={`font-bold uppercase tracking-wider text-[10px] flex items-center gap-2 ${colors.split(' ')[1]}`}>
                                [{c.severity}] {c.entity_hint}
                            </span>
                            <span className="text-[10px] font-mono opacity-60 text-slate-300">{(c.nli_score * 100).toFixed(0)}% CONF</span>
                        </div>
                        
                        <div className="p-4">
                            <div className="space-y-4 mb-5">
                                <div>
                                    <div className="text-[9px] text-slate-500 uppercase font-bold mb-1 tracking-wider">🖥️ {c.system_a.name}</div>
                                    <div className="font-mono text-xs text-slate-300 leading-relaxed bg-slate-950/50 p-2 rounded border border-slate-800/50">"{c.system_a.claim}"</div>
                                </div>
                                <div>
                                    <div className="text-[9px] text-slate-500 uppercase font-bold mb-1 tracking-wider">🖥️ {c.system_b.name}</div>
                                    <div className="font-mono text-xs text-slate-300 leading-relaxed bg-slate-950/50 p-2 rounded border border-slate-800/50">"{c.system_b.claim}"</div>
                                </div>
                            </div>

                            {!resolutions[c.id] ? (
                                <button 
                                    onClick={() => loadResolution(c.id)}
                                    disabled={loadingId === c.id}
                                    className="w-full bg-blue-600/10 hover:bg-blue-600/20 border border-blue-500/30 text-blue-400 py-2 rounded-lg font-medium text-xs transition-all disabled:opacity-50"
                                >
                                    {loadingId === c.id ? 'Analyzing...' : 'Generate Resolution Proposal'}
                                </button>
                            ) : (
                                <div className="pt-4 border-t border-slate-800/80 space-y-4 animate-in fade-in slide-in-from-top-2">
                                    <div>
                                        <h4 className="text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1">Diagnosis</h4>
                                        <p className="text-slate-300 text-xs leading-relaxed">{resolutions[c.id].why_they_contradict}</p>
                                    </div>
                                    <div className="bg-red-950/20 border border-red-500/10 p-3 rounded-lg">
                                        <h4 className="text-[9px] font-bold text-red-500 uppercase tracking-wider mb-1">Business Risk</h4>
                                        <p className="text-red-400 text-xs leading-relaxed">{resolutions[c.id].risk_reason}</p>
                                    </div>
                                    <div className="bg-green-950/20 border border-green-500/10 p-3 rounded-lg">
                                        <h4 className="text-[9px] font-bold text-green-500 uppercase tracking-wider mb-1">Remediation Target</h4>
                                        <p className="text-green-400 text-xs leading-relaxed mb-2">{resolutions[c.id].recommended_action}</p>
                                        <code className="block text-[10px] bg-black/60 border border-green-500/20 px-2 py-1.5 rounded text-green-300 font-mono overflow-x-auto [&::-webkit-scrollbar]:h-1 [&::-webkit-scrollbar-thumb]:bg-green-900">
                                            {resolutions[c.id].target_uri}
                                        </code>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )})}
            </div>
        </div>
    );
}