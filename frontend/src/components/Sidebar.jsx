import React from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, GitCommit, Inbox, Settings, Database } from 'lucide-react';

const Sidebar = () => {
  const navClass = ({ isActive }) => 
    `flex items-center gap-3 px-4 py-3 rounded-lg font-medium transition-colors ${isActive ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`;

  return (
    <div className="w-64 bg-slate-900 border-r border-slate-800 h-screen flex flex-col p-4">
      <div className="flex items-center gap-3 mb-10 px-2">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white tracking-tighter">O</div>
        <span className="text-xl font-bold text-white tracking-tight">Orqestra</span>
      </div>
      
      <nav className="flex flex-col gap-2">
        <NavLink to="/" className={navClass}>
          <Activity size={20} /> Live Feed
        </NavLink>
        <NavLink to="/resolutions" className={navClass}>
          <Inbox size={20} /> Resolutions
        </NavLink>
        <NavLink to="/graph" className={navClass}>
          <GitCommit size={20} /> Topology Graph
        </NavLink>
        <NavLink to="/explorer" className={navClass}>
          <Database size={20} /> Data Explorer
        </NavLink>
      </nav>

      <div className="mt-auto">
        <button className="flex items-center gap-3 px-4 py-3 text-slate-500 hover:text-slate-300 transition-colors w-full">
          <Settings size={20} /> Settings
        </button>
      </div>
    </div>
  );
};

export default Sidebar;