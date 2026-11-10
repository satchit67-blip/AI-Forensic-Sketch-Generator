import { useRef } from 'react';
export default function TiltCard({ children, className = '', max = 5 }) {
  const ref = useRef(null);
  const move = (e) => {
    const b = ref.current.getBoundingClientRect();
    const x = (e.clientX - b.left) / b.width - 0.5, y = (e.clientY - b.top) / b.height - 0.5;
    ref.current.style.transform = `perspective(1100px) rotateX(${-y * max}deg) rotateY(${x * max}deg)`;
  };
  const leave = () => (ref.current.style.transform = 'perspective(1100px) rotateX(0) rotateY(0)');
  return (
    <div ref={ref} onMouseMove={move} onMouseLeave={leave} className={`transition-transform duration-200 will-change-transform ${className}`}>
      {children}
    </div>
  );
}
