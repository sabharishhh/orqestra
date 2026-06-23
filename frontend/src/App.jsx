import EstateScoreHeader from './components/EstateScoreHeader';
import ContradictionFeed from './components/ContradictionFeed';
import KnowledgeGraph from './components/KnowledgeGraph';

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-blue-500/30 pb-12">
      {/* Expanded to max-w-[95rem] for an ultra-wide Command Center feel */}
      <div className="max-w-[95rem] mx-auto px-6 py-8">
        <header className="mb-8 flex flex-col md:flex-row md:items-end justify-between border-b border-slate-800/80 pb-6">
          <div>
            <h1 className="text-4xl font-extrabold text-white tracking-tight">
              Orqestra <span className="text-blue-500">Estate Control</span>
            </h1>
            <p className="text-slate-400 mt-2 text-lg">Continuous Asynchronous Semantic Monitoring</p>
          </div>
          <div className="mt-4 md:mt-0 px-4 py-2 bg-slate-900 border border-slate-800 rounded-full text-xs font-mono text-slate-500">
            v3.0.0-rc1
          </div>
        </header>
        
        <EstateScoreHeader />
        
        {/* The Split-Pane Layout */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
          {/* SIDEBAR: The Live Feed (1/3 width) */}
          <div className="xl:col-span-4 flex flex-col">
            <ContradictionFeed />
          </div>
          
          {/* MAIN PANE: The Graph (2/3 width) */}
          <div className="xl:col-span-8 flex flex-col">
            <KnowledgeGraph />
          </div>
        </div>

      </div>
    </div>
  );
}

export default App;