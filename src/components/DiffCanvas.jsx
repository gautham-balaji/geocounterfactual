import React, { useEffect, useRef, useState } from 'react';

/**
 * Change-amplification layer.
 *
 * The core problem this solves: a real diffusion run alters ~3.6% of the
 * scene (7,129 px of 195,328), and at display size that is invisible. A
 * viewer concludes "nothing happened" and the whole premise of the project
 * -- letting a planner SEE the outcome -- fails at the last step.
 *
 * So we compute |after - before| per pixel in a canvas, multiply by a gain,
 * and ramp it through a heat colour scale. Everything runs client-side:
 * both PNGs are same-origin through the Vite proxy, so getImageData is not
 * tainted and no backend round-trip is needed.
 */
export default function DiffCanvas({ beforeSrc, afterSrc, gain = 6,
                                     visible = true, className = '' }) {
  const canvasRef = useRef(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!visible || !beforeSrc || !afterSrc) return;
    let cancelled = false;

    const load = (src) => new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`failed to load ${src}`));
      img.src = src;
    });

    (async () => {
      try {
        const [a, b] = await Promise.all([load(beforeSrc), load(afterSrc)]);
        if (cancelled) return;

        const w = Math.min(a.naturalWidth, b.naturalWidth);
        const h = Math.min(a.naturalHeight, b.naturalHeight);
        if (!w || !h) throw new Error('zero-sized raster');

        const grab = (img) => {
          const c = document.createElement('canvas');
          c.width = w; c.height = h;
          const g = c.getContext('2d', { willReadFrequently: true });
          g.drawImage(img, 0, 0, w, h);
          return g.getImageData(0, 0, w, h).data;
        };

        const pa = grab(a);
        const pb = grab(b);

        const out = canvasRef.current;
        if (!out) return;
        out.width = w; out.height = h;
        const ctx = out.getContext('2d');
        const img = ctx.createImageData(w, h);

        for (let i = 0; i < pa.length; i += 4) {
          // Mean absolute difference across RGB, amplified.
          const d = (Math.abs(pa[i] - pb[i]) +
                     Math.abs(pa[i + 1] - pb[i + 1]) +
                     Math.abs(pa[i + 2] - pb[i + 2])) / 3;
          const v = Math.min(255, d * gain);
          // Black -> magenta -> amber -> white ramp. Reads clearly over both
          // the red-soil and green-vegetation parts of these scenes.
          img.data[i]     = Math.min(255, v * 1.9);
          img.data[i + 1] = Math.max(0, v * 1.25 - 90);
          img.data[i + 2] = Math.max(0, v * 1.6 - 40);
          // Transparent where nothing changed, so the scene shows through.
          img.data[i + 3] = v < 6 ? 0 : Math.min(255, 40 + v * 2.2);
        }
        ctx.putImageData(img, 0, 0);
        setError(null);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();

    return () => { cancelled = true; };
  }, [beforeSrc, afterSrc, gain, visible]);

  if (!visible) return null;

  if (error) {
    return (
      <div className="absolute bottom-16 left-4 z-30 px-2 py-1 rounded bg-rose-950/80 border border-rose-500/50 text-[10px] font-mono text-rose-200">
        Δ unavailable: {error}
      </div>
    );
  }

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 w-full h-full object-cover pointer-events-none ${className}`}
    />
  );
}
