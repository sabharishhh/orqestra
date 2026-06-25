import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ContradictionFeed from './components/ContradictionFeed';
import KnowledgeGraph from './components/KnowledgeGraph';
import ResolutionsQueue from './components/ResolutionsQueue';
import EstateScoreHeader from './components/EstateScoreHeader';
import DatabaseExplorer from './components/DatabaseExplorer';
import Sidebar from './components/Sidebar';
import './App.css';

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-slate-950 text-slate-200 font-sans overflow-hidden">
        <Sidebar />
        
        <div className="flex-1 flex flex-col h-full overflow-hidden">
          <EstateScoreHeader />
          
          <main className="flex-1 overflow-y-auto p-8">
            <Routes>
              <Route path="/" element={<ContradictionFeed />} />
              <Route path="/resolutions" element={<ResolutionsQueue />} />
              <Route path="/graph" element={<KnowledgeGraph />} />
              <Route path="/explorer" element={<DatabaseExplorer />} />
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  );
}

export default App;