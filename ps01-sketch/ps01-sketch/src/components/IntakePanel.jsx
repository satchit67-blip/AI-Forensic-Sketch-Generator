import { useRef, useState } from 'react';
import { Mic, MicOff, Wand2 } from 'lucide-react';

export default function IntakePanel({ description, setDescription, onGenerate, loading }) {
  const [listening, setListening] = useState(false);
  const rec = useRef(null);

  const toggleMic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return alert('Voice input needs a browser with the Web Speech API (Chrome or Edge).');
    if (listening) { rec.current?.stop(); return setListening(false); }
    rec.current = new SR();
    rec.current.continuous = true;
    rec.current.onresult = (e) => {
      const text = Array.from(e.results).slice(e.resultIndex).map((r) => r[0].transcript).join(' ');
      setDescription((d) => (d ? d + ' ' : '') + text.trim());
    };
    rec.current.onend = () => setListening(false);
    rec.current.start();
    setListening(true);
  };

  return (
    <aside className="glass flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-sm font-semibold uppercase tracking-wider text-slate-300">Witness description</h2>
        <button onClick={toggleMic} aria-pressed={listening} className={`btn !px-3 !py-1.5 ${listening ? '!border-red-400 text-red-300' : ''}`}>
          {listening ? <MicOff size={15} /> : <Mic size={15} />}{listening ? 'Stop' : 'Voice'}
        </button>
      </div>
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={11}
        placeholder="Describe the suspect in your own words, e.g. “Man in his 40s, sharp jaw, short grey hair, thin face…”"
        className="w-full resize-none rounded-xl border border-white/10 bg-black/40 p-3 font-mono text-xs leading-relaxed placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none" />
      {listening && <p className="font-mono text-[11px] text-red-300">● Listening… speak the description</p>}
      <button onClick={onGenerate} disabled={loading} className="btn btn-primary w-full">
        <Wand2 size={16} />{loading ? 'Generating…' : 'Generate Face'}
      </button>
    </aside>
  );
}
