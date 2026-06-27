import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ContradictionFeed from './components/ContradictionFeed';
import KnowledgeGraph from './components/KnowledgeGraph';
import ResolutionsQueue from './components/ResolutionsQueue';
import DatabaseExplorer from './components/DatabaseExplorer';
import Sidebar from './components/Sidebar';

export default function App() {
  return (
    <Router>
      <div className="flex h-screen bg-[var(--color-surface-0)] text-[var(--color-text-body)] overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<ContradictionFeed />} />
            <Route path="/resolutions" element={<ResolutionsQueue />} />
            <Route path="/graph" element={<KnowledgeGraph />} />
            <Route path="/explorer" element={<DatabaseExplorer />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}