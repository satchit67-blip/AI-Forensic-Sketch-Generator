import { useEffect, useRef } from 'react';

const mk = (n, seed) => Array.from({ length: n }, (_, i) => ({ x: (i * 97.3 + seed * 31) % 100, y: (i * 53.7 + seed * 17) % 100, r: 0.6 + ((i + seed) % 3) * 0.5 }));
const layers = [mk(90, 1), mk(60, 2), mk(35, 3)];

// Fixed space backdrop: stars and glowing rings drift at different speeds as the page scrolls.
export default function Background() {
  const ring = useRef(null);
  const star = [useRef(null), useRef(null), useRef(null)];
  useEffect(() => {
    let raf;
    const update = () => {
      const y = window.scrollY;
      ring.current.style.transform = `translate3d(${-y * 0.1}px, ${-y * 0.4}px, 0) rotate(${y * 0.05}deg)`;
      star.forEach((r, i) => (r.current.style.transform = `translate3d(0, ${-y * (0.06 + i * 0.1)}px, 0)`));
    };
    const onScroll = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(update); };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => { window.removeEventListener('scroll', onScroll); cancelAnimationFrame(raf); };
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden bg-[radial-gradient(900px_500px_at_75%_0%,#0b2a2a_0%,transparent_60%)]" aria-hidden="true">
      {layers.map((l, i) => (
        <svg key={i} ref={star[i]} className="absolute left-0 top-0 h-[400vh] w-full will-change-transform" style={{ animation: `twinkle ${5 + i * 3}s ease-in-out infinite` }} preserveAspectRatio="none">
          {l.map((s, k) => <circle key={k} cx={`${s.x}%`} cy={`${s.y}%`} r={s.r} fill="#bffcf2" opacity={0.55 + i * 0.15} />)}
        </svg>
      ))}
      <div ref={ring} className="absolute right-[-10%] top-[8%] h-[70vmin] w-[90vmin] will-change-transform">
        <div className="h-full w-full" style={{ animation: 'spin-slow 120s linear infinite' }}>
          <svg viewBox="0 0 600 400" className="h-full w-full" fill="none" stroke="#4fe6d2">
            <ellipse cx="300" cy="200" rx="290" ry="120" strokeOpacity=".35" transform="rotate(-18 300 200)" />
            <ellipse cx="300" cy="200" rx="240" ry="95" strokeOpacity=".28" transform="rotate(-18 300 200)" />
            <ellipse cx="300" cy="200" rx="190" ry="150" strokeOpacity=".22" transform="rotate(24 300 200)" />
            <ellipse cx="300" cy="200" rx="140" ry="60" strokeOpacity=".3" transform="rotate(-18 300 200)" />
          </svg>
        </div>
      </div>
    </div>
  );
}
