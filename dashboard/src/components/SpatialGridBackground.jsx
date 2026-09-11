import { useEffect, useRef } from 'react';

/**
 * SpatialGridBackground
 * High-performance 3D spatial interactive dot grid with perspective elevation,
 * smooth spring/lerp physics, and tactical amber-gold ambient radiance.
 */
export function SpatialGridBackground({
  active = true,
  containerRef,
  spacing = 18,
  influenceRadius = 170,
  maxElevation = 36,
  perspective = 280,
  className = '',
  style = {},
}) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const parent = containerRef?.current || canvas.parentElement;
    if (!parent) return;

    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let animId = null;
    let isDestroyed = false;

    // Grid points array
    let points = [];
    let width = 0;
    let height = 0;
    let dpr = 1;

    // Smoothed pointer physics state
    const mouse = {
      x: -9999,
      y: -9999,
      targetX: -9999,
      targetY: -9999,
      active: false,
      idleTime: 0,
      waveOffset: 0,
    };

    const initGrid = () => {
      const rect = parent.getBoundingClientRect();
      width = Math.max(rect.width, 100);
      height = Math.max(rect.height, 100);
      dpr = Math.min(window.devicePixelRatio || 1, 2);

      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      const cols = Math.ceil(width / spacing) + 3;
      const rows = Math.ceil(height / spacing) + 3;
      const startX = -spacing;
      const startY = -spacing;

      points = [];
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const gx = startX + c * spacing;
          const gy = startY + r * spacing;
          points.push({
            gx,
            gy,
            x: gx,
            y: gy,
            z: 0,
            targetZ: 0,
            factor: 0,
          });
        }
      }

      // Default initial idle target near top-right
      if (!mouse.active) {
        mouse.targetX = width * 0.75;
        mouse.targetY = Math.min(180, height * 0.25);
        mouse.x = mouse.targetX;
        mouse.y = mouse.targetY;
      }
    };

    initGrid();

    // Pointer events on the container
    const handlePointerMove = (e) => {
      const rect = parent.getBoundingClientRect();
      mouse.targetX = e.clientX - rect.left;
      mouse.targetY = e.clientY - rect.top;
      mouse.active = true;
      mouse.idleTime = 0;
    };

    const handlePointerLeave = () => {
      mouse.active = false;
      mouse.idleTime = 0;
      // Gently move target to top right idle rest point
      mouse.targetX = width * 0.85;
      mouse.targetY = Math.min(140, height * 0.2);
    };

    parent.addEventListener('pointermove', handlePointerMove, { passive: true });
    parent.addEventListener('pointerleave', handlePointerLeave, { passive: true });

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      if (!isDestroyed) {
        initGrid();
      }
    });
    resizeObserver.observe(parent);

    // Animation render loop
    let lastTime = performance.now();

    const render = (time) => {
      if (isDestroyed) return;

      const delta = Math.min((time - lastTime) / 1000, 0.1);
      lastTime = time;

      if (!active) {
        // Paused when closed/hidden
        animId = requestAnimationFrame(render);
        return;
      }

      // Smooth pointer lerp
      const lerpSpeed = mouse.active ? 0.12 : 0.04;
      mouse.x += (mouse.targetX - mouse.x) * lerpSpeed;
      mouse.y += (mouse.targetY - mouse.y) * lerpSpeed;

      // Ambient idle breathing wave when resting
      mouse.waveOffset += delta * 1.5;
      const breathingPulse = Math.sin(mouse.waveOffset) * 0.5 + 0.5;

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);

      const radSq = influenceRadius * influenceRadius;

      // Update and draw spatial points
      for (let i = 0; i < points.length; i++) {
        const pt = points[i];
        const dx = pt.gx - mouse.x;
        const dy = pt.gy - mouse.y;
        const distSq = dx * dx + dy * dy;

        let targetZ = 0;
        let factor = 0;

        if (distSq < radSq) {
          const dist = Math.sqrt(distSq);
          const norm = 1 - dist / influenceRadius;
          // Smooth cubic ease for natural convex spatial curvature
          factor = norm * norm * (3 - 2 * norm);
          targetZ = factor * maxElevation;
        } else if (!mouse.active) {
          // Subtle organic ambient ripple across points when pointer is idle
          const ambientWave = Math.sin(mouse.waveOffset + (pt.gx + pt.gy) * 0.02) * 1.5;
          targetZ = Math.max(0, ambientWave);
        }

        // Smooth spring lerp for each individual dot
        pt.z += (targetZ - pt.z) * 0.18;
        pt.factor += (factor - pt.factor) * 0.18;

        // 3D Perspective projection:
        // As point lifts closer to the viewer (z > 0), scale increases and displaces outward
        const pz = Math.max(-50, Math.min(pt.z, perspective - 10));
        const scale = perspective / (perspective - pz);

        // Spatial lateral warp (convex dome effect)
        const push = pt.factor * 7.5;
        const dist = Math.hypot(dx, dy) || 1;
        const targetX = pt.gx + (dx / dist) * push;
        const targetY = pt.gy + (dy / dist) * push;

        pt.x += (targetX - pt.x) * 0.18;
        pt.y += (targetY - pt.y) * 0.18;

        // Visual radius: fine micro-dots (slightly smaller), grows smoothly in 3D
        const baseRadius = 0.9;
        const curRadius = Math.max(0.7, (baseRadius + pt.factor * 1.85) * scale);

        // Alpha & color based on 3D depth factor:
        // Tastefully softened lighting to keep ambient presence without high-contrast glare
        const ambientAlpha = 0.28 + (!mouse.active ? breathingPulse * 0.04 : 0);
        const alpha = Math.min(0.80, ambientAlpha + pt.factor * (0.80 - ambientAlpha));

        // Draw clean spatial dot (no outer circles)
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, curRadius, 0, Math.PI * 2);
        if (pt.factor > 0.45) {
          // Warm tactical gold highlight (softened from bright white-gold)
          ctx.fillStyle = `rgba(240, 202, 142, ${alpha})`;
        } else if (pt.factor > 0.12) {
          // Subtle warm amber
          ctx.fillStyle = `rgba(220, 168, 98, ${alpha})`;
        } else {
          // Ambient resting grid dot: subtle structured gold-bronze
          ctx.fillStyle = `rgba(188, 142, 85, ${alpha})`;
        }
        ctx.fill();
      }

      ctx.restore();
      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      isDestroyed = true;
      if (animId) cancelAnimationFrame(animId);
      parent.removeEventListener('pointermove', handlePointerMove);
      parent.removeEventListener('pointerleave', handlePointerLeave);
      resizeObserver.disconnect();
    };
  }, [active, containerRef, spacing, influenceRadius, maxElevation, perspective]);

  return (
    <canvas
      ref={canvasRef}
      className={`spatial-grid-canvas ${className}`}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 0,
        ...style,
      }}
      aria-hidden="true"
    />
  );
}
