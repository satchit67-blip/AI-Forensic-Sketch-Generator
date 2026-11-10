export const DISGUISES = ['Full Beard', 'Mustache', 'Wire-Rimmed Glasses', 'Sunglasses', 'Long Hair', 'Bald', 'Scar/Mark'];
export const CASE_ID = '#HACK26-451';
export const OFFICER = 'Officer Anubhav Kashyap';

export const HAIR_STYLES = { 'Short hair': 'short', 'Long hair': 'long', Bald: 'bald' };
export const HAIR_COLORS = { Black: '#1c1c20', Brown: '#4a3426', Blond: '#b9a06a', Grey: '#8a8a90', Red: '#8a3b22' };
export const FEATURES = [
  { key: 'jaw', label: 'Jawline Width' },
  { key: 'eyeSize', label: 'Eye Size' },
  { key: 'eyeSpacing', label: 'Eye Spacing' },
  { key: 'noseWidth', label: 'Nose Width' },
  { key: 'noseLength', label: 'Nose Length' },
  { key: 'lips', label: 'Lip Fullness' },
  { key: 'brow', label: 'Brow Height' },
  { key: 'ageLines', label: 'Age Lines' },
];
export const defaultFeatures = { jaw: 50, eyeSize: 50, eyeSpacing: 50, noseWidth: 50, noseLength: 50, lips: 50, brow: 50, ageLines: 20 };
export const defaultTraits = { jaw: 'soft', hair: 'short', hairColor: HAIR_COLORS.Black, face: 1, features: defaultFeatures };

const COLOR_WORDS = { Black: /black|dark/, Brown: /brown/, Blond: /blond|fair/, Grey: /gr[ae]y/, Red: /red|ginger|auburn/ };

// Rule-based interpreter: maps witness or refinement language to trait changes so core identity is preserved.
export function interpret(text, traits) {
  const s = text.toLowerCase();
  const t = { ...traits, features: { ...defaultFeatures, ...traits.features } };
  const f = t.features;
  const add = [], remove = [], notes = [];
  const has = (re) => re.test(s);
  const nudge = (key, delta, note) => {
    const next = Math.max(0, Math.min(100, f[key] + delta));
    if (next !== f[key]) { f[key] = next; notes.push(note); }
  };

  if (has(/sharp|square|angular|strong jaw|chiseled/)) { t.jaw = 'sharp'; notes.push('jaw sharpened'); }
  if (has(/round|soft jaw|chubby/)) { t.jaw = 'soft'; notes.push('jaw softened'); }
  if (has(/wide jaw|broad jaw/)) nudge('jaw', 20, 'jaw widened');
  if (has(/narrow jaw|thin jaw/)) nudge('jaw', -20, 'jaw narrowed');

  if (has(/long hair|ponytail|shoulder.length/)) { t.hair = 'long'; notes.push('hair lengthened'); }
  if (has(/short hair|crew cut|buzz/)) { t.hair = 'short'; notes.push('hair shortened'); }
  if (has(/bald|shaved head/)) { t.hair = 'bald'; notes.push('hairline cleared'); }
  for (const [name, re] of Object.entries(COLOR_WORDS)) {
    if (re.test(s)) { t.hairColor = HAIR_COLORS[name]; notes.push(`hair colour → ${name.toLowerCase()}`); break; }
  }

  if (has(/nose.*(narrow|thin)/)) nudge('noseWidth', -20, 'nose narrowed');
  if (has(/nose.*(wide|broad|flat)/)) nudge('noseWidth', 20, 'nose widened');
  if (has(/nose.*long|long nose|big nose/)) nudge('noseLength', 20, 'nose lengthened');
  if (has(/nose.*short|short nose|small nose/)) nudge('noseLength', -20, 'nose shortened');
  if (has(/big eyes|bigger eyes|large eyes|wide eyes/)) nudge('eyeSize', 20, 'eyes enlarged');
  if (has(/small eyes|smaller eyes/)) nudge('eyeSize', -20, 'eyes reduced');
  if (has(/eyes closer|close.set eyes/)) nudge('eyeSpacing', -15, 'eyes moved closer');
  if (has(/eyes (wider|farther)|wide.set eyes/)) nudge('eyeSpacing', 15, 'eyes spread apart');
  if (has(/full lips|fuller lips|plump/)) nudge('lips', 20, 'lips fuller');
  if (has(/thin lips|thinner lips/)) nudge('lips', -20, 'lips thinner');
  if (has(/high brow|raised brow|arched/)) nudge('brow', 15, 'brows raised');
  if (has(/low brow|heavy brow|furrowed/)) nudge('brow', -15, 'brows lowered');
  if (has(/wrinkle|age line|older|elderly|aged/)) nudge('ageLines', 30, 'age lines added');
  if (has(/young|smooth skin|no wrinkles/)) nudge('ageLines', -30, 'age lines reduced');

  if (has(/no beard|clean.shaven/)) remove.push('Full Beard', 'Mustache');
  else {
    if (has(/beard|stubble/)) add.push('Full Beard');
    if (has(/mustache|moustache/)) add.push('Mustache');
  }
  if (has(/sunglasses|shades/)) add.push('Sunglasses');
  else if (has(/glasses|spectacles/)) add.push('Wire-Rimmed Glasses');
  if (has(/scar|mark|mole/)) add.push('Scar/Mark');
  add.forEach((a) => notes.push(`added ${a.toLowerCase()}`));
  return { traits: t, add, remove, notes };
}

// Long Hair and Bald are mutually exclusive.
export function toggleSet(set, name, force) {
  const next = new Set(set);
  const on = force ?? !next.has(name);
  on ? next.add(name) : next.delete(name);
  if (on && name === 'Bald') next.delete('Long Hair');
  if (on && name === 'Long Hair') next.delete('Bald');
  return next;
}
export const stamp = () => new Date().toISOString().replace('T', ' ').slice(0, 19) + 'Z';
