import { Map as MapIcon, Menu } from 'lucide-react';

export function Navbar() {
  return (
    <nav className="absolute top-0 left-0 right-0 z-40 p-6 flex justify-between items-center pointer-events-none">
      <div className="flex items-center gap-3 pointer-events-auto">
        <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center text-white shadow-[0_10px_25px_rgb(15,23,42,0.25)]">
          <MapIcon size={20} strokeWidth={2.5} />
        </div>
        <span className="font-bold text-xl tracking-tight text-slate-800 drop-shadow-sm bg-white/50 px-2 py-1 rounded backdrop-blur-sm">
          TopoPuzzle 3D
        </span>
      </div>

      <div className="hidden md:flex items-center gap-8 glass-panel px-6 py-3 rounded-full pointer-events-auto">
        <a href="#" className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors">
          Gallery
        </a>
        <a href="#" className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors">
          How to Print
        </a>
        <div className="w-px h-4 bg-slate-200"></div>
        <a href="#" className="text-sm font-medium text-slate-800 hover:text-slate-900 transition-colors">
          Login
        </a>
      </div>

      <button className="md:hidden glass-panel p-3 rounded-full pointer-events-auto">
        <Menu size={20} className="text-slate-800" />
      </button>
    </nav>
  );
}

