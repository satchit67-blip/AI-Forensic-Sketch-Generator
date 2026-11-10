import { useOutletContext } from 'react-router-dom';
import AuditLog from '../components/AuditLog';

export default function AuditPage() {
  const s = useOutletContext();
  return (
    <>
      <section className="px-1 pb-2 pt-4">
        <p className="font-mono text-xs text-nexus-cyan">MODULE 03</p>
        <h2 className="mt-1 text-4xl font-bold tracking-tight sm:text-5xl">Audit trail</h2>
        <p className="mt-3 max-w-2xl text-slate-400">Chain of custody for this case. Every generation, disguise change, refinement and export is recorded here.</p>
      </section>
      <AuditLog logs={s.logs} />
    </>
  );
}
