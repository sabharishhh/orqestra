import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Estate from './components/Estate';
import Canon from './components/Canon';
import ContradictionFeed from './components/ContradictionFeed';
import KnowledgeGraph from './components/KnowledgeGraph';
import ResolutionsQueue from './components/ResolutionsQueue';
import DatabaseExplorer from './components/DatabaseExplorer';
import Sidebar from './components/Sidebar';
import Build from './components/Build';

export default function App() {
    return (
        <Router>
            <div className="flex h-screen bg-[var(--color-surface-0)] text-[var(--color-text-body)] overflow-hidden">
                <Sidebar />
                <main className="flex-1 overflow-hidden">
                    <Routes>
                        <Route path="/build" element={<Build />} />
                        <Route path="/" element={<Navigate to="/estate" replace />} />
                        <Route path="/estate" element={<Estate />} />
                        <Route path="/canon" element={<Canon />} />
                        <Route path="/feed" element={<ContradictionFeed />} />
                        <Route path="/resolutions" element={<ResolutionsQueue />} />
                        <Route path="/graph" element={<KnowledgeGraph />} />
                        <Route path="/explorer" element={<DatabaseExplorer />} />
                    </Routes>
                </main>
            </div>
        </Router>
    );
}