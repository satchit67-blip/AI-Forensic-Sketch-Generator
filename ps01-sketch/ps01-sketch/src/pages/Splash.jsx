import { useNavigate } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { Fingerprint, Power } from 'lucide-react';
import Background from '../components/Background';

const face = 'absolute inset-0 grid place-items-center rounded-full border-4 border-nexus-cyan bg-nexus-900 text-nexus-cyan shadow-glow';

export default function Splash() {
  const nav = useNavigate();
  const still = useReducedMotion();
  return (
    <div className="relative grid min-h-screen place-items-center p-4">
      <Background />
      <div className="relative z-10 flex w-full max-w-5xl flex-col items-center gap-10 px-4 text-center">
        <div style={{ perspective: 1000 }}>
          <motion.div className="relative h-44 w-44" style={{ transformStyle: 'preserve-3d' }}
            animate={still ? undefined : { rotateY: 360 }} transition={{ repeat: Infinity, duration: 6, ease: 'linear' }}>
            <div className={face} style={{ backfaceVisibility: 'hidden' }}><Fingerprint size={84} /></div>
            <div className={face} style={{ backfaceVisibility: 'hidden', transform: 'rotateY(180deg)' }}><Fingerprint size={84} /></div>
          </motion.div>
        </div>
        <div>
          <h1 className="text-wrap break-words text-4xl font-bold leading-tight tracking-tight md:text-5xl lg:text-6xl px-4">AI NEXUS <span className="text-nexus-cyan">//</span> Forensic Sketch Synthesizer</h1>
          <p className="mt-2 font-mono text-xs text-slate-400">Identity verified · Case #HACK26-451</p>
        </div>
        <button className="btn btn-primary !px-6 !py-3 text-base" onClick={() => nav('/studio')}><Power size={18} />Initialize System</button>
      </div>
    </div>
  );
}
