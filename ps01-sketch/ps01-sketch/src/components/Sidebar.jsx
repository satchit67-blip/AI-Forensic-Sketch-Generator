import { NavLink } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { Fingerprint, ScanFace, Drama, ScrollText } from 'lucide-react';

const items = [
  { to: '/studio', label: 'Sketch studio', icon: ScanFace },
  { to: '/disguise-toolkit', label: 'Disguise toolkit', icon: Drama },
  { to: '/audit-trail', label: 'Audit trail', icon: ScrollText },
];

export default function Sidebar() {
  const still = useReducedMotion();
  return (
    <aside className="glass fixed bottom-3 left-3 top-3 z-20 hidden w-56 flex-col p-4 lg:flex">
      <div className="mb-6 flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-nexus-cyan text-nexus-950"><Fingerprint size={20} /></span>
        <div><p className="text-sm font-bold leading-tight">AI NEXUS</p><p className="text-[11px] text-slate-400">Forensic Sketch</p></div>
      </div>
      <p className="mb-2 px-2 text-xs text-slate-500">Workspace</p>
      <nav className="flex flex-col gap-1">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to}
            className={({ isActive }) => `flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${isActive ? 'bg-nexus-cyan text-nexus-950' : 'text-slate-300 hover:bg-white/5'}`}>
            <Icon size={16} />{label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto flex justify-center pt-4" style={{ perspective: 600 }}>
        <motion.div aria-label="AI NEXUS logo" role="img"
          className="grid h-14 w-14 place-items-center rounded-xl border border-nexus-cyan/60 bg-nexus-900 text-nexus-cyan shadow-glow"
          style={{ transformStyle: 'preserve-3d' }}
          animate={still ? undefined : { rotateY: 360 }}
          transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}>
          <Fingerprint size={26} />
        </motion.div>
      </div>
    </aside>
  );
}
