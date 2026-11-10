import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useScroll, useSpring, useTransform } from 'framer-motion';
import { ChevronDown, Fingerprint, LogIn } from 'lucide-react';
import Background from '../components/Background';
import HeadScene from '../components/HeadScene';
import TiltCard from '../components/TiltCard';

const EASE = [0.16, 1, 0.3, 1];

export default function Login() {
  const nav = useNavigate();
  const [badge, setBadge] = useState('');
  const [pw, setPw] = useState('');
  const [err, setErr] = useState('');

  // Scroll-linked motion: headline parallax, quote drift and the smoothed progress that drives the 3D head.
  const { scrollY, scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 70, damping: 22, mass: 1.1 });
  const line1X = useTransform(scrollY, [0, 900], [-40, 0]);
  const line2X = useTransform(scrollY, [0, 900], [40, 0]);
  const heroOpacity = useTransform(scrollY, [0, 600], [1, 0]);
  const heroY = useTransform(scrollY, [0, 600], [0, -140]);
  const quoteX = useTransform(scrollY, [800, 1800], [240, -240]);

  const submit = (e) => {
    e.preventDefault();
    if (!badge.trim() || !pw) return setErr('Enter both your Officer Badge ID and password.');
    // Demo gateway: swap this for a real auth call. The password is never stored.
    sessionStorage.setItem('nexus_badge', badge.trim());
    nav('/splash');
  };

  const goLogin = () => document.getElementById('login')?.scrollIntoView({ behavior: 'smooth' });

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#02050a] text-slate-200">
      <Background />
      <HeadScene progress={progress} />

      <div className="fixed left-6 top-5 z-20 font-mono text-[11px] tracking-widest text-slate-400">
        <span className="text-cyan-300">AI NEXUS</span> // FORENSIC SKETCH SYNTHESIZER
      </div>

      {/* Hero */}
      <section className="relative z-10 flex min-h-screen w-full max-w-full flex-col justify-center overflow-hidden px-8 sm:px-12 lg:px-20">
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: EASE }}
          className="font-mono text-xs tracking-[0.35em] text-cyan-300">● SECURE GATEWAY · CASE #HACK26-451</motion.p>
        <motion.h1 style={{ opacity: heroOpacity, y: heroY }}
          className="mt-6 w-full max-w-full whitespace-normal text-wrap break-words font-black uppercase leading-tight tracking-tighter text-5xl md:text-6xl lg:text-8xl">
          <motion.span initial={{ opacity: 0, y: 120 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1.4, ease: EASE }}
            style={{ x: line1X }} className="block">witness</motion.span>
          <motion.span initial={{ opacity: 0, y: 120 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1.4, delay: 0.15, ease: EASE }}
            style={{ x: line2X }} className="block text-cyan-300">words to a face</motion.span>
        </motion.h1>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.2, duration: 1 }}
          className="mt-8 max-w-xl text-base text-slate-300 sm:text-lg">
          Describe the suspect in your own words. The system renders a forensic composite you can refine, disguise and export.
        </motion.p>
        <div className="mt-10 flex flex-wrap items-center gap-4">
          <button onClick={goLogin} className="btn btn-primary !px-6 !py-3 text-base">Enter secure gateway</button>
          <span className="font-mono text-[11px] text-slate-500">Scroll ↓</span>
        </div>
        <motion.div animate={{ y: [0, 10, 0] }} transition={{ repeat: Infinity, duration: 1.8 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 text-cyan-300/70">
          <ChevronDown />
        </motion.div>
      </section>

      {/* Parallax statement */}
      <section className="relative z-10 flex min-h-[110vh] items-center px-6 sm:px-12 lg:px-20">
        <motion.div style={{ x: quoteX }} className="max-w-3xl">
          <p className="font-mono text-xs tracking-[0.3em] text-slate-500">01 · INTAKE</p>
          <p className="mt-4 text-4xl font-bold leading-tight sm:text-6xl">Voice in. <span className="text-cyan-300">Composite out.</span></p>
        </motion.div>
      </section>

      {/* Login */}
      <section id="login" className="relative z-10 flex min-h-screen items-center justify-center px-4 py-24" style={{ perspective: 1400 }}>
        <motion.div initial={{ opacity: 0, y: 160, rotateX: 25, scale: 0.9 }} whileInView={{ opacity: 1, y: 0, rotateX: 0, scale: 1 }}
          viewport={{ once: true, amount: 0.35 }} transition={{ duration: 1.3, ease: EASE }} className="w-full max-w-sm">
          <TiltCard max={4}>
            <form onSubmit={submit} className="glass flex flex-col gap-4 p-7">
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-cyan-300 text-nexus-950"><Fingerprint size={24} /></span>
                <div><h1 className="text-lg font-bold leading-tight">Officer sign-in</h1><p className="font-mono text-[11px] text-slate-400">Secure access only</p></div>
              </div>
              <label className="text-sm">Officer Badge ID
                <input value={badge} onChange={(e) => setBadge(e.target.value)} autoComplete="username" placeholder="e.g. PD-40517"
                  className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm focus:border-cyan-400/60 focus:outline-none" />
              </label>
              <label className="text-sm">Password
                <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" placeholder="••••••••"
                  className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm focus:border-cyan-400/60 focus:outline-none" />
              </label>
              {err && <p role="alert" className="text-xs text-red-300">{err}</p>}
              <button className="btn btn-primary"><LogIn size={16} />Sign in</button>
              <p className="text-center font-mono text-[11px] text-slate-500">Access is logged · Case #HACK26-451</p>
            </form>
          </TiltCard>
        </motion.div>
      </section>
    </div>
  );
}
