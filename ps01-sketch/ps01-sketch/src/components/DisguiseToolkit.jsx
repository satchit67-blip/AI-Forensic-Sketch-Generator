import { Smile, Minus, Glasses, EyeOff, Wind, CircleDot, Slash, ScanFace } from 'lucide-react';
import FaceSketch from './FaceSketch';
import ErrorBoundary from './ErrorBoundary';
import { defaultTraits } from '../lib/face';

const tools = [
  { name: 'Full Beard', icon: Smile, note: 'Covers jaw and chin' },
  { name: 'Mustache', icon: Minus, note: 'Upper-lip hair' },
  { name: 'Wire-Rimmed Glasses', icon: Glasses, note: 'Thin metal frames' },
  { name: 'Sunglasses', icon: EyeOff, note: 'Hides the eyes' },
  { name: 'Long Hair', icon: Wind, note: 'Shoulder length' },
  { name: 'Bald', icon: CircleDot, note: 'Removes all hair' },
  { name: 'Scar/Mark', icon: Slash, note: 'Scar across the cheek' },
];

const noop = () => {};

// Safe default export: tolerates missing or malformed props, so it always renders.
export default function DisguiseToolkit({ id, active, onToggle = noop, generated = false, traits, imageUrl }) {
  const activeSet = active instanceof Set ? active : new Set(Array.isArray(active) ? active : []);
  const safeTraits = { ...defaultTraits, ...(traits || {}) };

  return (
    <section id={id} className="glass p-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-2xl font-semibold">Disguise &amp; facial modification</h2>
          <p className="mt-1 max-w-xl text-sm text-slate-400">Toggle a modification to see how the suspect might look disguised. You can also drag any tile onto the sketch canvas.</p>
        </div>
        <span className="rounded-full border border-nexus-cyan/40 bg-nexus-cyan/10 px-3 py-1 font-mono text-xs text-nexus-cyan">
          {activeSet.size} of {tools.length} active
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {tools.map(({ name, icon, note }) => {
            const Icon = icon || ScanFace;
            const on = activeSet.has(name);
            return (
              <button
                key={name}
                type="button"
                draggable
                onDragStart={(e) => e.dataTransfer.setData('text/plain', name)}
                onClick={() => onToggle(name)}
                aria-pressed={on}
                className={`group flex cursor-grab items-center gap-3 rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5 active:cursor-grabbing ${on ? 'border-nexus-cyan bg-nexus-cyan/10 shadow-glow' : 'border-white/10 bg-black/30 hover:border-nexus-cyan/50'}`}
              >
                <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${on ? 'bg-nexus-cyan text-nexus-950' : 'bg-white/5 text-nexus-cyan'}`}>
                  <Icon size={20} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{name}</span>
                  <span className="block text-xs text-slate-400">{note}</span>
                </span>
                <span className={`font-mono text-[10px] ${on ? 'text-nexus-cyan' : 'text-slate-500'}`}>{on ? 'ON' : 'OFF'}</span>
              </button>
            );
          })}
        </div>

        <div className="mx-auto aspect-[5/6] w-full max-w-[260px] overflow-hidden rounded-2xl border border-white/15 bg-black/40">
          {generated ? (
            <ErrorBoundary>
              {imageUrl ? (
                <img src={imageUrl} alt="Suspect preview" className="h-full w-full object-cover" />
              ) : (
                <FaceSketch traits={safeTraits} disguises={activeSet} />
              )}
            </ErrorBoundary>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center text-xs text-slate-400">
              <ScanFace size={32} className="text-nexus-cyan/60" />
              Generate a sketch to preview disguises here.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
