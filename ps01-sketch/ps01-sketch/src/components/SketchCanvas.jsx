import { useState } from 'react';
import { RotateCcw, Download, ZoomIn, ZoomOut, ScanFace, Loader2, AlertTriangle } from 'lucide-react';
import TiltCard from './TiltCard';
import FaceSketch from './FaceSketch';

const SLOTS = 5;

export default function SketchCanvas({ imageUrl, error, onImageError, generated, loading, traits, disguises, svgRef, onSynth, onReset, onExport, onDropDisguise, versions = [], onRestore = () => {} }) {
  const safeVersions = Array.isArray(versions) ? versions : [];
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState(null);
  const [over, setOver] = useState(false);
  const clamp = (z) => Math.min(3, Math.max(0.6, z));

  return (
    <section className="glass flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn" onClick={() => { onReset(); setZoom(1); setPan({ x: 0, y: 0 }); }} disabled={loading}><RotateCcw size={16} />Reset Canvas</button>
        <div className="ml-auto flex items-center gap-1">
          <button className="btn !px-2" aria-label="Zoom out" onClick={() => setZoom((z) => clamp(z - 0.2))}><ZoomOut size={16} /></button>
          <span className="w-12 text-center font-mono text-xs">{Math.round(zoom * 100)}%</span>
          <button className="btn !px-2" aria-label="Zoom in" onClick={() => setZoom((z) => clamp(z + 0.2))}><ZoomIn size={16} /></button>
        </div>
      </div>

      <TiltCard>
        <div
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); const n = e.dataTransfer.getData('text/plain'); if (n) onDropDisguise(n); }}
          onWheel={(e) => setZoom((z) => clamp(z - e.deltaY * 0.0015))}
          onPointerDown={(e) => setDrag({ x: e.clientX - pan.x, y: e.clientY - pan.y })}
          onPointerMove={(e) => drag && setPan({ x: e.clientX - drag.x, y: e.clientY - drag.y })}
          onPointerUp={() => setDrag(null)} onPointerLeave={() => setDrag(null)}
          className={`relative mx-auto aspect-[5/6] w-full max-w-md cursor-grab touch-none overflow-hidden rounded-2xl border bg-black/40 shadow-glow transition-colors active:cursor-grabbing ${over ? 'border-cyan-400' : 'border-white/15'}`}
        >
          <div className="pointer-events-none absolute inset-0 z-10 bg-[linear-gradient(transparent_95%,rgba(79,230,210,.12)_95%)] bg-[length:100%_24px]" />
          {error ? (
            <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <AlertTriangle size={40} className="text-red-400" />
              <p className="font-mono text-sm text-red-300">Sketch synthesis failed</p>
              <p className="text-xs text-slate-300">{error}</p>
              <button className="btn" onClick={onSynth} disabled={loading}><RotateCcw size={14} />Try again</button>
            </div>
          ) : generated ? (
            <div className="h-full w-full transition-transform duration-100" style={{ transform: `translate(${pan.x}px,${pan.y}px) scale(${zoom})` }}>
              {imageUrl
                ? <img src={imageUrl} alt="Generated suspect sketch" onError={onImageError} draggable={false} className="h-full w-full object-cover" />
                : <FaceSketch traits={traits} disguises={disguises} svgRef={svgRef} />}
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-slate-400">
              <ScanFace size={48} className="text-cyan-400/60" />
              <p className="font-mono text-sm">No sketch yet</p>
              <p className="text-xs">Enter a witness description, then choose Generate Face.</p>
            </div>
          )}
          {loading && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-[#0a0b10]/75 backdrop-blur-sm">
              <Loader2 className="animate-spin text-cyan-400" size={36} />
              <p className="font-mono text-sm text-cyan-300">Synthesizing facial features…</p>
            </div>
          )}
        </div>
      </TiltCard>
      <p className="text-center font-mono text-[11px] text-slate-500">Scroll to zoom · drag to pan · drop disguise chips here</p>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="font-mono text-xs uppercase tracking-wider text-slate-400">Versions - select one to restore</p>
          <span className="font-mono text-[11px] text-slate-500">{safeVersions.length}/{SLOTS}</span>
        </div>
        <div className="grid grid-cols-5 gap-2">
          {Array.from({ length: SLOTS }, (_, i) => {
            const v = safeVersions[i];
            return v ? (
              <button key={v.id} onClick={() => onRestore(v)} title={`Restore: ${v.label}`}
                className="aspect-square overflow-hidden rounded-xl border border-white/10 bg-black/40 transition hover:-translate-y-0.5 hover:border-cyan-400/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400">
                {v.imageUrl ? <img src={v.imageUrl} alt="" className="h-full w-full object-cover" /> : <FaceSketch traits={v.traits} disguises={new Set(v.disguises)} />}
                <span className="sr-only">{v.label}</span>
              </button>
            ) : (
              <div key={`empty-${i}`} className="grid aspect-square place-items-center rounded-xl border border-dashed border-white/10 font-mono text-[10px] text-slate-600">V{i + 1}</div>
            );
          })}
        </div>
      </div>

      <button className="btn btn-primary w-full" onClick={onExport} disabled={!generated || loading}><Download size={16} />Export High-Res Sketch</button>
    </section>
  );
}
