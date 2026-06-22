import { useEffect, useState } from 'react';
import { fetchROI } from '../api';

export default function EstateScoreHeader() {
    const [roi, setRoi] = useState(null);

    useEffect(() => {
        // Initial fetch, then poll every 5 seconds for real-time dashboard feel
        fetchROI().then(setRoi).catch(console.error);
        const interval = setInterval(() => fetchROI().then(setRoi).catch(console.error), 5000);
        return () => clearInterval(interval);
    }, []);

    if (!roi) return <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl text-slate-400 animate-pulse">Establishing Telemetry Link...</div>;

    return (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg">
                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider mb-2">Active Conflicts</div>
                <div className="text-4xl font-bold text-white">{roi.active_contradictions}</div>
            </div>
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg">
                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider mb-2">Critical / High</div>
                <div className="text-4xl font-bold text-orange-400">
                    <span className="text-red-500">{roi.severity_breakdown.critical}</span> / {roi.severity_breakdown.high}
                </div>
            </div>
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg">
                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider mb-2">Financial Exposure</div>
                <div className="text-4xl font-bold text-green-400">${roi.total_financial_exposure_usd.toLocaleString()}</div>
            </div>
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg flex flex-col justify-center">
                <div className="text-slate-400 text-sm font-semibold uppercase tracking-wider mb-2">Platform Status</div>
                <div className="text-lg font-bold text-blue-400 flex items-center mt-1">
                    <span className="relative flex h-3 w-3 mr-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
                    </span>
                    Monitoring Live
                </div>
            </div>
        </div>
    );
}