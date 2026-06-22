import EstateScoreHeader from './components/EstateScoreHeader';
import ContradictionFeed from './components/ContradictionFeed';
import KnowledgeGraph from './components/KnowledgeGraph';

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-blue-500/30 pb-20">
      <div className="max-w-7xl mx-auto px-6 py-12">
        <header className="mb-12 flex flex-col md:flex-row md:items-end justify-between border-b border-slate-800 pb-6">
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
        
        {/* The New 3D Visualizer */}
        <KnowledgeGraph />
        
        <main>
          <ContradictionFeed />
        </main>
      </div>
    </div>
  );
}

export default App;