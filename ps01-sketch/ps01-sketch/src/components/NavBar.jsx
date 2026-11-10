import { Cpu, ShieldCheck, ScrollText, Fingerprint } from 'lucide-react';
import { CASE_ID } from '../lib/face';
const Badge = ({ icon: Icon, label }) => (
  <span className="inline-flex items-center gap-1.5 rounded-full border border-nexus-cyan/30 bg-nexus-cyan/10 px-2.5 py-1 font-mono text-[11px] text-nexus-cyan">
    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-nexus-cyan" /><Icon size={12} />{label}
  </span>
);
export default function NavBar() {
  return (
    <header className="glass sticky top-3 z-20 flex flex-wrap items-center justify-between gap-3 px-5 py-3">
      <div className="flex items-center gap-3">
        <Fingerprint className="text-nexus-cyan" size={28} />
        <h1 className="font-mono text-base font-bold tracking-tight sm:text-lg">AI NEXUS <span className="text-nexus-cyan">//</span> Forensic Sketch Synthesizer</h1>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-lg border border-white/15 bg-black/30 px-2.5 py-1 font-mono text-xs">Case ID: {CASE_ID}</span>
        <Badge icon={Cpu} label="GPU Active" />
        <Badge icon={ShieldCheck} label="SHA-256 Secured" />
        <Badge icon={ScrollText} label="Audit Log Online" />
      </div>
    </header>
  );
}
