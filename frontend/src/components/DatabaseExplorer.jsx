import React, { useState, useEffect } from 'react';

export default function DatabaseExplorer() {
  const [table, setTable] = useState('systems');
  const [data, setData] = useState([]);
  const tables = ["systems", "entities", "claims", "contradictions", "resolution_proposals", "coherence_scores", "contrastive_feedback"];

  useEffect(() => {
    fetch(`http://localhost:8000/admin/table/${table}`)
      .then(res => res.json())
      .then(setData);
  }, [table]);

  return (
    <div className="p-6 bg-slate-900 min-h-screen text-white">
      <div className="flex gap-4 mb-6">
        {tables.map(t => (
          <button key={t} onClick={() => setTable(t)} className={`px-4 py-2 rounded ${table === t ? 'bg-blue-600' : 'bg-slate-800'}`}>
            {t}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs uppercase bg-slate-800">
            <tr>{data[0] && Object.keys(data[0]).map(k => <th key={k} className="px-4 py-2">{k}</th>)}</tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-b border-slate-700">
                {Object.values(row).map((val, j) => <td key={j} className="px-4 py-2 truncate max-w-[200px]">{JSON.stringify(val)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}