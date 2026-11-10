import { useOutletContext } from 'react-router-dom';
import DisguiseToolkit from '../components/DisguiseToolkit';
import ErrorBoundary from '../components/ErrorBoundary';

export default function DisguisePage() {
  const s = useOutletContext() || {};
  return (
    <>
      <section className="px-1 pb-2 pt-4">
        <p className="font-mono text-xs text-nexus-cyan">MODULE 02</p>
        <h2 className="mt-1 text-4xl font-bold tracking-tight sm:text-5xl">Disguise toolkit</h2>
      </section>
      <ErrorBoundary>
        <DisguiseToolkit
          active={s.disguises}
          onToggle={s.toggleDisguise}
          generated={s.generated}
          traits={s.traits}
          imageUrl={s.imageUrl}
        />
      </ErrorBoundary>
    </>
  );
}
