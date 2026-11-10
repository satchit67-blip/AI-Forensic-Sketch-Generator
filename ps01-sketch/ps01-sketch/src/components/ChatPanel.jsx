import { useEffect, useRef, useState } from 'react';
import { Send, Bot, UserRound, BadgeCheck } from 'lucide-react';

const roleStyle = {
  Witness: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  Officer: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  'AI System': 'border-nexus-cyan/40 bg-nexus-cyan/10 text-nexus-cyan',
};
const RoleIcon = ({ role }) => (role === 'AI System' ? <Bot size={12} /> : role === 'Officer' ? <BadgeCheck size={12} /> : <UserRound size={12} />);

export default function ChatPanel({ messages, onSend, busy }) {
  const [text, setText] = useState('');
  const [role, setRole] = useState('Witness');
  const end = useRef(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  const submit = (e) => { e.preventDefault(); if (!text.trim() || busy) return; onSend(role, text.trim()); setText(''); };

  return (
    <aside className="glass flex h-[640px] flex-col p-5 lg:h-auto lg:min-h-[640px]">
      <h2 className="mb-3 font-mono text-sm font-semibold">Chat refinement</h2>
      <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`rounded-xl border p-3 ${m.role === 'AI System' ? 'border-white/10 bg-black/30' : 'border-white/10 bg-white/5'}`}>
            <div className="mb-1.5 flex items-center justify-between">
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px] ${roleStyle[m.role]}`}><RoleIcon role={m.role} />{m.role}</span>
              <time className="font-mono text-[10px] text-slate-500">{m.time}</time>
            </div>
            <p className="text-sm leading-relaxed text-slate-200">{m.text}</p>
          </div>
        ))}
        <div ref={end} />
      </div>
      <form onSubmit={submit} className="mt-3 space-y-2">
        <div className="flex gap-2">
          {['Witness', 'Officer'].map((r) => (
            <button type="button" key={r} onClick={() => setRole(r)} aria-pressed={role === r} className={`chip !cursor-pointer ${role === r ? 'chip-on' : ''}`}>{r}</button>
          ))}
        </div>
        <div className="flex gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Make the nose narrower" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-xs focus:border-nexus-cyan/60 focus:outline-none" />
          <button className="btn btn-primary" disabled={busy} aria-label="Send feedback"><Send size={16} /></button>
        </div>
      </form>
    </aside>
  );
}
