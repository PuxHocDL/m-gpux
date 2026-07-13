import { useEffect, useRef } from "react";

/**
 * ClickSpark — a full-screen overlay that bursts warm sparks wherever the user
 * clicks. It also listens for a custom `mgpux:spark` event so other components
 * (e.g. the tutorial) can fire celebratory bursts:
 *   window.dispatchEvent(new CustomEvent("mgpux:spark", { detail: { x, y, count, colors } }))
 */
export default function ClickSpark() {
  const canvasRef = useRef(null);
  const sparks = useRef([]);
  const raf = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const palette = ["#F97316", "#FB923C", "#FDBA74", "#FBBF24", "#FCD34D"];

    const resize = () => {
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();

    const burst = (x, y, count = 12, colors = palette) => {
      for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 * i) / count + Math.random() * 0.5;
        const speed = 2.4 + Math.random() * 3.6;
        sparks.current.push({
          x,
          y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          life: 1,
          size: 1.6 + Math.random() * 2.4,
          color: colors[(Math.random() * colors.length) | 0],
        });
      }
    };

    const onClick = (e) => burst(e.clientX, e.clientY);
    const onCustom = (e) => {
      const { x, y, count, colors } = e.detail || {};
      burst(
        x ?? window.innerWidth / 2,
        y ?? window.innerHeight / 3,
        count ?? 28,
        colors ?? palette
      );
    };

    const draw = () => {
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      sparks.current = sparks.current.filter((s) => s.life > 0);
      for (const s of sparks.current) {
        s.x += s.vx;
        s.y += s.vy;
        s.vy += 0.12; // gravity
        s.vx *= 0.98;
        s.life -= 0.022;
        ctx.globalAlpha = Math.max(0, s.life);
        ctx.fillStyle = s.color;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf.current = requestAnimationFrame(draw);
    };
    draw();

    window.addEventListener("pointerdown", onClick);
    window.addEventListener("mgpux:spark", onCustom);
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf.current);
      window.removeEventListener("pointerdown", onClick);
      window.removeEventListener("mgpux:spark", onCustom);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-[100]"
      style={{ width: "100vw", height: "100vh" }}
    />
  );
}
