import { ShieldCheck } from 'lucide-react';
export default function AuditLog({ logs }) {
  return (
    <section className="glass p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-mono text-sm font-semibold"><ShieldCheck size={16} className="text-nexus-cyan" />Secure access audit log</h2>
        <span className="font-mono text-[11px] text-slate-400">{logs.length} entries · chain of custody</span>
      </div>
      <div className="max-h-64 overflow-auto rounded-xl border border-white/10">
        <table className="w-full min-w-[640px] text-left font-mono text-xs">
          <thead className="sticky top-0 bg-nexus-900/95 text-slate-400">
            <tr>{['Timestamp', 'User', 'Case ID', 'Action Performed'].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {logs.map((l, i) => (
              <tr key={i} className="border-t border-white/5 transition-colors hover:bg-white/5">
                <td className="whitespace-nowrap px-3 py-2 text-slate-400">{l.ts}</td>
                <td className="px-3 py-2">{l.user}</td>
                <td className="px-3 py-2 text-nexus-cyan">{l.caseId}</td>
                <td className="px-3 py-2">{l.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
