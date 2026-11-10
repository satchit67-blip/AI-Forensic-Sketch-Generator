import { useRef, useState } from 'react';
import { CASE_ID, OFFICER, defaultTraits, interpret, toggleSet, stamp } from './face';
import { generateSketch, applyDisguise, refineSketch, exportAudit } from './api';

const now = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const welcome = {
  role: 'AI System',
  time: now(),
  text: 'Session open. Describe the suspect, then synthesize a sketch. Later feedback edits only the traits you mention, so the core face stays the same.',
};

// Shared case state. Lives in the dashboard layout so it survives route changes.
export function useStudio() {
  const [description, setDescription] = useState('');
  const [traits, setTraits] = useState(defaultTraits);
  const [disguises, setDisguises] = useState(new Set());
  const [generated, setGenerated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [imageUrl, setImageUrl] = useState(null);
  const [messages, setMessages] = useState([welcome]);
  const [logs, setLogs] = useState([{ ts: stamp(), user: OFFICER, caseId: CASE_ID, action: 'Opened Case Session' }]);
  const svgRef = useRef(null);

  const log = (action) => setLogs((l) => [{ ts: stamp(), user: OFFICER, caseId: CASE_ID, action }, ...l]);
  const say = (role, text) => setMessages((m) => [...m, { role, text, time: now() }]);

  const applyText = (text) => {
    const r = interpret(text, traits);
    setTraits(r.traits);
    let d = disguises;
    r.add.forEach((a) => (d = toggleSet(d, a, true)));
    r.remove.forEach((a) => (d = toggleSet(d, a, false)));
    setDisguises(d);
    return r;
  };

  const synth = async () => {
    const trimmed = (description || '').trim();
    if (!trimmed) {
      return say('AI System', 'Add a witness description first so there is something to synthesize.');
    }
    setError('');
    setLoading(true);
    try {
      const activeDisguisesList = Array.from(disguises);
      const result = await generateSketch(trimmed, activeDisguisesList, traits);
      if (result.traits) {
        setTraits(result.traits);
      } else {
        applyText(trimmed);
      }
      setImageUrl(result.imageUrl);
      setGenerated(true);
      log('Generated Initial Sketch (AI Pipeline)');
      const notesStr = result.notes && result.notes.length ? result.notes.join(', ') : 'Structured facial traits extracted.';
      say('AI System', `Initial sketch synthesized. ${notesStr}`);
    } catch (err) {
      console.warn('Synthesis API notice, using procedural fallback:', err);
      const r = applyText(trimmed);
      setGenerated(true);
      log('Generated Initial Sketch');
      say('AI System', `Initial sketch generated. ${r.notes.length ? 'Applied: ' + r.notes.join(', ') + '.' : 'Default features retained.'}`);
    } finally {
      setLoading(false);
    }
  };

  const toggleDisguise = async (name) => {
    if (!generated) {
      return say('AI System', 'Synthesize an initial sketch before applying disguises.');
    }
    const on = !disguises.has(name);
    const nextSet = toggleSet(disguises, name, on);
    setDisguises(nextSet);
    log(`${on ? 'Applied' : 'Removed'} Disguise: ${name}`);
    say('AI System', `${on ? 'Applied' : 'Removed'} ${name}. Core facial structure updated with ${name.toLowerCase()}.`);

    setLoading(true);
    try {
      const nextDisguisesArr = Array.from(nextSet);
      const result = await applyDisguise(name, on, description, { ...traits, disguises: nextDisguisesArr });
      if (result.imageUrl) {
        setImageUrl(result.imageUrl);
      }
      if (result.traits) {
        setTraits(result.traits);
      }
    } catch (err) {
      console.warn('Network disguise update notice:', err);
    } finally {
      setLoading(false);
    }
  };

  const feedback = async (role, text) => {
    say(role, text);
    if (!generated) {
      return say('AI System', 'No active sketch. Synthesize an initial sketch first.');
    }
    setLoading(true);
    try {
      const result = await refineSketch(text, traits, role, description);
      if (result.imageUrl) {
        setImageUrl(result.imageUrl);
      }
      if (result.traits) {
        setTraits(result.traits);
      }
      log(`Refinement by ${role}: "${text.slice(0, 40)}${text.length > 40 ? '…' : ''}"`);
      say('AI System', result.summary || 'Traits updated. Identity anchors preserved.');
    } catch (err) {
      console.warn('Refinement API notice:', err);
      const r = applyText(text);
      log(`Refinement by ${role}: "${text.slice(0, 40)}${text.length > 40 ? '…' : ''}"`);
      const notesStr = Array.isArray(r.notes) && r.notes.length ? r.notes.join(', ') : '';
      say('AI System', notesStr ? `Updated: ${notesStr}. Identity anchors preserved.` : 'Feedback recorded.');
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setError('');
    setImageUrl(null);
    setTraits(defaultTraits);
    setDisguises(new Set());
    setGenerated(false);
    log('Reset Canvas');
    say('AI System', 'Canvas cleared.');
  };

  const onImageError = () => {
    console.warn('Image failed to render, falling back to procedural SVG');
    setImageUrl(null);
  };

  const exportPng = () => {
    exportAudit();
    if (imageUrl) {
      const a = document.createElement('a');
      a.href = imageUrl;
      a.download = `suspect-sketch-${CASE_ID.slice(1)}.png`;
      a.target = '_blank';
      a.click();
      return log('Exported High-Res Image');
    }
    if (!svgRef.current) return;
    const xml = new XMLSerializer().serializeToString(svgRef.current);
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = 2400;
      c.height = 2880;
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      c.toBlob((b) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(b);
        a.download = `suspect-sketch-${CASE_ID.slice(1)}.png`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
      log('Exported High-Res Image');
    };
    img.onerror = () => setError('Export failed. Please try again.');
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
  };

  return {
    description,
    setDescription,
    traits,
    disguises,
    generated,
    loading,
    error,
    imageUrl,
    messages,
    logs,
    svgRef,
    synth,
    toggleDisguise,
    feedback,
    reset,
    exportPng,
    onImageError,
  };
}
