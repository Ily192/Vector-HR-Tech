import { useEffect, useRef } from "react";

type Node = { x: number; y: number; vx: number; vy: number; r: number };

const LINK_DISTANCE = 140;
const AQUA = "62, 236, 235";
const INK = "142, 157, 244";

/** Red de nodos en aqua que deriva lentamente: la "constelación" de vectorhrtech.com. */
export function Constellation({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let nodes: Node[] = [];
    let width = 0;
    let height = 0;
    let frame = 0;
    let visible = true;
    const pointer = { x: -9999, y: -9999 };

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.round(Math.min(90, (width * height) / 16000));
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        r: Math.random() * 1.6 + 1,
      }));
    };

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i] as Node;
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j] as Node;
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < LINK_DISTANCE) {
            ctx.strokeStyle = `rgba(${INK}, ${0.22 * (1 - d / LINK_DISTANCE)})`;
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
        const near = Math.hypot(a.x - pointer.x, a.y - pointer.y) < 160;
        if (near) {
          ctx.strokeStyle = `rgba(${AQUA}, 0.35)`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(pointer.x, pointer.y);
          ctx.stroke();
        }
        ctx.fillStyle = `rgba(${AQUA}, ${near ? 0.95 : 0.55})`;
        ctx.beginPath();
        ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const step = () => {
      for (const n of nodes) {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > width) n.vx *= -1;
        if (n.y < 0 || n.y > height) n.vy *= -1;
      }
      draw();
      if (visible) frame = requestAnimationFrame(step);
    };

    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = e.clientX - rect.left;
      pointer.y = e.clientY - rect.top;
    };
    const onLeave = () => {
      pointer.x = -9999;
      pointer.y = -9999;
    };

    resize();
    draw();

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? false;
      cancelAnimationFrame(frame);
      if (visible && !reduceMotion) frame = requestAnimationFrame(step);
    });
    observer.observe(canvas);

    window.addEventListener("resize", resize);
    canvas.parentElement?.addEventListener("pointermove", onMove);
    canvas.parentElement?.addEventListener("pointerleave", onLeave);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", resize);
      canvas.parentElement?.removeEventListener("pointermove", onMove);
      canvas.parentElement?.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  // biome-ignore lint/a11y/noAriaHiddenOnFocusable: un canvas sin tabIndex no recibe el foco; es decorativo.
  return <canvas ref={ref} aria-hidden="true" className={`pointer-events-none ${className}`} />;
}
