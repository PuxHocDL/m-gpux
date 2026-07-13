import { useRef, useState } from "react";

/**
 * SpotlightCard — a warm radial glow tracks the pointer across the card surface.
 */
export default function SpotlightCard({ children, className = "", spotlight = "rgba(251,146,60,0.18)" }) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ x: -200, y: -200 });
  const [active, setActive] = useState(false);

  const onMove = (e) => {
    const rect = ref.current.getBoundingClientRect();
    setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      className={`group relative overflow-hidden ${className}`}
    >
      <div
        className="pointer-events-none absolute -inset-px opacity-0 transition-opacity duration-300"
        style={{
          opacity: active ? 1 : 0,
          background: `radial-gradient(220px circle at ${pos.x}px ${pos.y}px, ${spotlight}, transparent 70%)`,
        }}
      />
      <div className="relative">{children}</div>
    </div>
  );
}
