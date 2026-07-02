import { NavLink } from 'react-router-dom';
import { Boxes, BookMarked, Rss, CheckSquare, Share2, Database, ChevronDown, BookOpen, Settings, Wrench } from 'lucide-react';
const ORG_SLUG = 'demo-fitness'; // TODO: pull from context once org switcher is wired

const navItem = ({ isActive }) =>
    `relative flex items-center gap-3 h-10 px-4 text-[14px] font-medium transition-colors ${
        isActive
            ? 'bg-[var(--color-surface-2)] text-[var(--color-text-primary)] before:absolute before:left-0 before:top-0 before:h-full before:w-[2px] before:bg-[var(--color-accent)]'
            : 'text-[var(--color-text-body)] hover:text-[var(--color-text-primary)]'
    }`;

export default function Sidebar() {
    return (
        <aside className="w-60 shrink-0 bg-[var(--color-surface-1)] border-r border-[var(--color-border-default)] h-screen flex flex-col">
            {/* Brand */}
            <div className="h-14 px-4 flex items-center gap-2.5 border-b border-[var(--color-border-default)]">
                <span className="text-[16px] font-bold tracking-[-0.01em] text-[var(--color-accent)]">
                    ORQESTRA
                </span>
                <span className="font-mono text-[10px] tracking-[0.05em] text-[var(--color-text-tertiary)] uppercase">
                    preview_build
                </span>
            </div>

            {/* Org switcher */}
            <button className="h-12 px-4 flex items-center justify-between border-b border-[var(--color-border-default)] hover:bg-[var(--color-surface-2)] transition-colors">
                <div className="flex flex-col items-start">
                    <span className="text-[10px] font-bold tracking-[0.05em] uppercase text-[var(--color-text-tertiary)]">
                        Organization
                    </span>
                    <span className="font-mono text-[13px] text-[var(--color-text-primary)]">
                        {ORG_SLUG}
                    </span>
                </div>
                <ChevronDown size={16} className="text-[var(--color-text-secondary)]" />
            </button>

            {/* Primary nav */}
            <nav className="flex-1 py-2">
                <NavLink to="/build" className={navItem}>
                    <Wrench size={18} strokeWidth={1.5} /> Build
                </NavLink>
                <NavLink to="/estate" className={navItem}>
                    <Boxes size={18} strokeWidth={1.5} /> Estate
                </NavLink>
                <NavLink to="/canon" className={navItem}>
                    <BookMarked size={18} strokeWidth={1.5} /> Canon
                </NavLink>
                <NavLink to="/feed" className={navItem}>
                    <Rss size={18} strokeWidth={1.5} /> Feed
                </NavLink>
                <NavLink to="/resolutions" className={navItem}>
                    <CheckSquare size={18} strokeWidth={1.5} /> Resolutions
                </NavLink>
                <NavLink to="/graph" className={navItem}>
                    <Share2 size={18} strokeWidth={1.5} /> Graph
                </NavLink>
                <NavLink to="/explorer" className={navItem}>
                    <Database size={18} strokeWidth={1.5} /> Explorer
                </NavLink>
            </nav>

            {/* Footer */}
            <div className="border-t border-[var(--color-border-default)] py-2">
                <button className="flex items-center gap-3 h-10 px-4 w-full text-[14px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors">
                    <BookOpen size={18} strokeWidth={1.5} /> Docs
                </button>
                <button className="flex items-center gap-3 h-10 px-4 w-full text-[14px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors">
                    <Settings size={18} strokeWidth={1.5} /> Settings
                </button>
            </div>
        </aside>
    );
}