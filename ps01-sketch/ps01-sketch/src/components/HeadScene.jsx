import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// Abstract wireframe head: a sphere reshaped into a head-like silhouette (not an anatomical model).
function useHeadGeometry() {
  return useMemo(() => {
    const g = new THREE.SphereGeometry(1, 48, 36);
    const pos = g.attributes.position;
    const v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i);
      const bump = 1 + 0.035 * Math.sin(v.y * 8 + v.x * 4) * Math.cos(v.z * 6);
      let x = v.x * 0.78 * bump;
      const y = v.y * 1.18 * bump;
      const z = v.z * 0.92 * bump;
      if (v.y < -0.15) x *= 0.72; // narrower jaw and chin
      pos.setXYZ(i, x, y, z);
    }
    g.computeVertexNormals();
    return g;
  }, []);
}

function Head({ progress, mouse, reduce }) {
  const group = useRef();
  const geometry = useHeadGeometry();

  useFrame((_, dt) => {
    const g = group.current;
    if (!g) return;
    const p = progress.get();                 // 0 at top of page, 1 at the login card
    const m = mouse.current;
    if (!reduce.current) g.rotation.y += dt * 0.28;
    g.rotation.x += (m.y * 0.25 - g.rotation.x) * 0.05;
    g.rotation.z += (m.x * -0.06 - g.rotation.z) * 0.05;
    g.position.x += (1.6 - p * 1.0 + m.x * 0.2 - g.position.x) * 0.06;
    g.position.y += (-p * 0.8 + m.y * 0.1 - g.position.y) * 0.06;
    g.scale.setScalar(1.25 + p * 0.55);       // grows as the user scrolls down
  });

  return (
    <group ref={group}>
      <mesh geometry={geometry}>
        <meshBasicMaterial color="#4fe6d2" wireframe transparent opacity={0.5} />
      </mesh>
      <mesh rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[1.35, 0.008, 8, 160]} />
        <meshBasicMaterial color="#7af5e6" transparent opacity={0.6} />
      </mesh>
    </group>
  );
}

export default function HeadScene({ progress }) {
  const mouse = useRef({ x: 0, y: 0 });
  const reduce = useRef(false);

  useEffect(() => {
    reduce.current = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const onMove = (e) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.current.y = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 z-[1]">
      <Canvas dpr={[1, 2]} camera={{ position: [0, 0, 5.2], fov: 40 }} gl={{ alpha: true, antialias: true }}>
        <Head progress={progress} mouse={mouse} reduce={reduce} />
      </Canvas>
    </div>
  );
}
