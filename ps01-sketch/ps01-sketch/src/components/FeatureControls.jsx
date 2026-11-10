import { useState } from 'react';

const SLIDERS = [
  ['JAWLINE WIDTH', 'jaw'], ['EYE SIZE', 'eyeSize'], ['EYE SPACING', 'eyeSpacing'], ['NOSE WIDTH', 'noseWidth'],
  ['NOSE LENGTH', 'noseLength'], ['LIP FULLNESS', 'lips'], ['BROW WEIGHT', 'brow'], ['AGE LINES', 'ageLines'],
];
const HAIR_STYLES = ['Short hair', 'Long hair', 'Crew cut', 'Bald'];
const HAIR_COLORS = ['Black', 'Brown', 'Blonde', 'Grey', 'Red'];

const initialSliders = Object.fromEntries(SLIDERS.map(([, k]) => [k, 50]));

const sectionHeader = 'font-mono text-[11px] uppercase tracking-[0.2em] text-slate-500';
const selectClass = 'w-full cursor-pointer rounded-lg border border-slate-700 bg-[#0a0d13] px-2.5 py-2 font-mono text-xs text-white transition-colors hover:border-slate-500 focus:border-sky-400 focus:outline-none';

export default function FeatureControls() {
  const [sliders, setSliders] = useState(initialSliders);
  const [hairStyle, setHairStyle] = useState('Short hair');
  const [hairColor, setHairColor] = useState('Black');
  const [glasses, setGlasses] = useState(false);
  const [moustache, setMoustache] = useState(false);

  const setSlider = (key) => (e) => setSliders((s) => ({ ...s, [key]: Number(e.target.value) }));

  return (
    <aside className="flex flex-col gap-6 rounded-2xl border border-white/10 bg-[#0d1117] p-5 font-mono shadow-lg shadow-black/40">
      <section className="flex flex-col gap-4">
        <h2 className={sectionHeader}>FEATURE CONTROLS</h2>
        {SLIDERS.map(([label, key]) => (
          <div key={key} className="grid grid-cols-[110px_1fr_36px] items-center gap-3">
            <span className="text-[11px] uppercase tracking-wide text-slate-400">{label}</span>
            <input type="range" min={0} max={100} value={sliders[key]} onChange={setSlider(key)} aria-label={label}
              className="nexus-range" style={{ '--p': `${sliders[key]}%` }} />
            <span className="text-right text-xs tabular-nums text-white">{sliders[key]}</span>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-4 border-t border-white/10 pt-5">
        <h2 className={sectionHeader}>HAIR, FACIAL HAIR AND ACCESSORIES</h2>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1.5 text-[11px] uppercase tracking-wide text-slate-400">
            Hair style
            <select value={hairStyle} onChange={(e) => setHairStyle(e.target.value)} className={selectClass}>
              {HAIR_STYLES.map((o) => <option key={o} value={o} className="bg-[#0a0d13]">{o}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-[11px] uppercase tracking-wide text-slate-400">
            Hair color
            <select value={hairColor} onChange={(e) => setHairColor(e.target.value)} className={selectClass}>
              {HAIR_COLORS.map((o) => <option key={o} value={o} className="bg-[#0a0d13]">{o}</option>)}
            </select>
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[['Glasses', glasses, setGlasses], ['Moustache', moustache, setMoustache]].map(([label, checked, set]) => (
            <label key={label} className="flex cursor-pointer items-center gap-2.5 text-xs text-slate-400 hover:text-slate-200">
              <input type="checkbox" checked={checked} onChange={(e) => set(e.target.checked)}
                className="h-4 w-4 shrink-0 cursor-pointer appearance-none rounded-[3px] border border-slate-600 bg-[#0a0d13] transition-colors checked:border-sky-400 checked:bg-sky-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400" />
              {label}
            </label>
          ))}
        </div>
      </section>
    </aside>
  );
}
