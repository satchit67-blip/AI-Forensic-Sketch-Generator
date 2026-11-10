import { useOutletContext } from 'react-router-dom';
import NavBar from '../components/NavBar';
import IntakePanel from '../components/IntakePanel';
import SketchCanvas from '../components/SketchCanvas';
import ChatPanel from '../components/ChatPanel';
import ErrorBoundary from '../components/ErrorBoundary';
import FeatureControls from '../components/FeatureControls';

export default function Studio() {
  const s = useOutletContext();
  return (
    <>
      <NavBar />
      <section className="px-1 pb-2 pt-4">
        <h2 className="text-4xl font-bold leading-[1.05] tracking-tight sm:text-6xl">Every witness detail,<br /><span className="text-nexus-cyan">one live sketch.</span></h2>
        <p className="mt-4 max-w-2xl text-slate-400">Describe the suspect, refine the face with live feedback, and test disguises. Every action is written to the chain-of-custody log.</p>
      </section>
      <main className="grid grid-cols-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)_300px]">
        <div className="flex flex-col gap-4">
          <IntakePanel description={s.description} setDescription={s.setDescription} onGenerate={s.synth} loading={s.loading} />
          <ChatPanel messages={s.messages} onSend={s.feedback} busy={s.loading} />
        </div>
        <ErrorBoundary>
          <SketchCanvas imageUrl={s.imageUrl} error={s.error} onImageError={s.onImageError} generated={s.generated} loading={s.loading}
            traits={s.traits} disguises={s.disguises} svgRef={s.svgRef} onSynth={s.synth} onReset={s.reset} onExport={s.exportPng} onDropDisguise={s.toggleDisguise} />
        </ErrorBoundary>
        <FeatureControls />
      </main>
    </>
  );
}
