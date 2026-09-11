import { useEffect, useRef } from 'react';

// Decoded 256x128 1-bit equirectangular land mask for authentic continent dot placement
const MAP_WIDTH = 256;
const MAP_HEIGHT = 128;
const WORLD_MAP_B64 = '////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////Dj///////6n////////////////////////////////8AAACAAAAgP8AP////////////////////////////8AAAP/gAAAAAAA+gf//////////////////////////wAAAfQAAAAAAAADg////////////////////g//////AAAAQAAAAGYAAAf8H//////////////////4AJ////8AAAAAAAAD4AAP//4AAfn/////////x/////4AB////wAAAAAAAAcAAL///gKAef////////+H/////8zD///+AAAAAAAAHAHH/////8A/AAO//P/+AAM//////+H///wAAAAAIAAcA//////////uAA/gP//z/5//////4f//+AAAAB/8AAB73//////////9/+D////////////w///gAAAAf//mf//f////////////+H////////////D//gAAAAD///f////////////////5////////////4P/4A/AAA/3+P////////////////CAf///////+8T/Af8AD8AAH+f/////////////////4AP////////ghTwA/gAAAAB/n//////////////////wA////////8APwAB8AAAAAP+f///////////////z/gAB/sX/////gA/mAAwAAAAA/4///////////////8OAAABeAD/////AD/8AAAAAAMBPB/////////////+ABwAAABkAH/////gH/wAAAAAAwDcf/////////////gAfAAAAQAAH/////wf/gAAAAADgPB/////////////4AB4AAAAAAAH/////3//wAAAAB3A///////////////8AHAAAAAAAAP/////P//gAAAAHeP///////////////8AYAAAAAAAAf///////8AAAAAB7////////////////wBAAAAAAAAA///////+YAAAAABf///////////////9gAAAAAAAAAB////v//DwAAAAAf/////5//////////0AAAAAAAAAAD///+P/8HAAAAAA/////+B/////////+QAAAAAAAAAAP////v/+AAAAAAB///9nwHf////////wAAAAAAAAAAB////2/9gAAAAAAH/v/ifj9////////+OAAAAAAAAAAH//////AAAAAAAP8nP8AfH/////////w4AAAAAAAAAAf/////8AAAAAAB/wnP3x+P////////4AAAAAAAAAAAA//////AAAAAAAH+CG7//4/////////AYAAAAAAAAAAD/////4AAAAAAAfwARn//j///////wYBgAAAAAAAAAAH/////AAAAAAAA+AmGf//P///////4wMAAAAAAAAAAAP////8AAAAAAAAj/AAF//////////DHwAAAAAAAAAAA/////gAAAAAAAH/8AAH/////////4J8AAAAAAAAAAAA////8AAAAAAAA//8GAf/////////wOAAAAAAAAAAAAB////AAAAAAAAH//8/L//////////gQAAAAAAAAAAAAG//+8AAAAAAAAf//////////////+AAAAAAAAAAAAAAP/8AYAAAAAAAD//////+////////4AAAAAAAAAAAAAAX/gBgAAAAAAA/////9/5////////AAAAAAAAAAAAAAAv+ACAAAAAAAD/////7/wf//////4AAAAAAAAAAAAAADf4AAAAAAAAAf/////v/uB//////IAAAAAAAAAAAAAAE/gBgAAAAAAD//////f/8B/////5gAAAAAAAAAAAAAAB+ADwAAAAAAP/////8//wH//f/+AAAAAAAAAAAAAAAAH4MBgAAAAAA//////7//AH/w/8gAAAAAAAAAAAAAAAAfxwA4AAAAAD//////n/4AP+B/mAAAAAAAAAAAAAAAAAf+ABAAAAAAP//////P/AA/gH/AGAAAAAAAAAAAAAAAAP4AAAAAAAA//////8/wAD8AX+AYAAAAAAAAAAAAAAAAD+AAAAAAAD//////78AAPgAf8BgAAAAAAAAAAAAAAAAD4AAAAAAAP///////AAAeAA/wDAAAAAAAAAAAAAAAAADgAAAAAAA///////gAAB4ACfADAAAAAAAAAAAAAAAAAGD+wAAAAB///////+AADgAI4AQAAAAAAAAAAAAAAAAAP//gAAAAD///////wAANAAhABQAAAAAAAAAAAAAAAAAb//AAAAAH///////AAAMADAAHAAAAAAAAAAAAAAAAAAH//AAAAAP//////4AAAwAGAMMAAAAAAAAAAAAAAAAAAf//gAAAAOw/////gAAAADcB4AAAAAAAAAAAAAAAAAAB///AAAAAAAf///8AAAAAOwPAAAAAAAAAAAAAAAAAAAP//8AAAAAAB////gAAAAAfB8AAAAAAAAAAAAAAAAAAB///4AAAAAAP///4AAAAAA8fzoAAAAAAAAAAAAAAAAAP///4AAAAAA//+/AAAAAABx/MGAAAAAAAAAAAAAAAAA////4AAAAAD//78AAAAAADz7gNgAAAAAAAAAAAAAAAB////+AAAAAH///gAAAAAAPHuO/4AAAAAAAAAAAAAAAP////8AAAAAP//8AAAAAAAYAcA/wAAAAAAAAAAAAAAAf////4AAAAAf//wAAAAAAAcAAA/sAAAAAAAAAAAAAAB/////gAAAAB///AAAAAAAA+AAD+AAAAAAAAAAAAAAAD////+AAAAAH//8AAAAAAAAADADMAAAAAAAAAAAAAAAP////wAAAAAP//4AAAAAAAAAAAAYAAAAAAAAAAAAAAAf///+AAAAAA///gAAAAAAAAAA4QAAAAAAAAAAAAAAAA////4AAAAAH//+DAAAAAAAAAPjAAAAAAAAAAAAAAAAD////gAAAAA///4cAAAAAAAAH+GAAAAAAAAAAAAAAAAH///8AAAAAD///jwAAAAAAAA/88AAAAAAAAAAAAAAAAH///wAAAAAP//4fAAAAAAAAH//wAAAgAAAAAAAAAAAAP///AAAAAAf//B4AAAAAAAA///gAAAAAAAAAAAAAAAA///4AAAAAB//4HgAAAAAAAf///AAAAAAAAAAAAAAAAD///gAAAAAD//gcAAAAAAAD///+AEAAAAAAAAAAAAAAP//8AAAAAAP//BwAAAAAAAf///8AAAAAAAAAAAAAAAA//+AAAAAAA//4HAAAAAAAB////wAAAAAAAAAAAAAAAH//wAAAAAAD//AAAAAAAAAH////gAAAAAAAAAAAAAAAf//AAAAAAAH/4AAAAAAAAAf///+AAAAAAAAAAAAAAAB//4AAAAAAAf/gAAAAAAAAB////4AAAAAAAAAAAAAAAH//AAAAAAAA/8AAAAAAAAAD////gAAAAAAAAAAAAAAAf/4AAAAAAAB/gAAAAAAAAAP///+AAAAAAAAAAAAAAAB//gAAAAAAAH8AAAAAAAAAA/gf/wAAAAAAAAAAAAAAAP/8AAAAAAAAdAAAAAAAAAADgAv/AAAAAAAAAAAAAAAA//AAAAAAAAAAAAAAAAAAAAAAAf4AAQAAAAAAAAAAAAD/8AAAAAAAAAAAAAAAAAAAAAAB/gAAgAAAAAAAAAAAAP/AAAAAAAAAAAAAAAAAAAAAAAB4AADgAAAAAAAAAAAB/wAAAAAAAAAAAAAAAAAAAAAAAAAAAMAAAAAAAAAAAAH+AAAAAAAAAAAAAAAAAAAAAAAAHAADAAAAAAAAAAAAAfwAAAAAAAAAAAAAAAAAAAAAAAAYAAcAAAAAAAAAAAAA/AAAAAAAAAAAAAAAAAAAAAAAAAAADAAAAAAAAAAAAAHwAAAAAAAAAAAAAAAAAAAAAAAAAAA4AAAAAAAAAAAAAfgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAeAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADwAAAAAAAAAAAAAAAAAHwAAAAAAAAAAAAAAAAAAAAAA8AAAAAAAAAAAAAAAAAg/gGB8AAAAAAAAAAAAAAAAAAfgAAAAAAAAAAAAfwAD///////8AAAAAAAAAAAAAAAAB/AAAAAAAAAAAA///8f////////4AAAAAAAAAAAAAAD/4AAAAAAAAPAf///////////////AAAAAAAAAAAAAAP/gAAAAA/////////////////////8AAAAAAAAAD/4D//AAAAA//////////////////////8AAAAABv/3P////4AAAAP//////////////////////wAAAA//////////4AAAH//////////////////////wAAAB///////////+AAH//////////////////////+AMA//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////w==';
const MAP_BYTES = typeof atob !== 'undefined'
  ? Uint8Array.from(atob(WORLD_MAP_B64), (c) => c.charCodeAt(0))
  : new Uint8Array(4096);

function isLand(lat, lon) {
  if (lat > 80 || lat < -76) return false;
  const x = Math.min(255, Math.max(0, Math.floor(((lon + 180) / 360) * MAP_WIDTH)));
  const y = Math.min(127, Math.max(0, Math.floor(((90 - lat) / 180) * MAP_HEIGHT)));
  const idx = y * MAP_WIDTH + x;
  return (MAP_BYTES[idx >> 3] & (1 << (7 - (idx & 7)))) !== 0;
}

export function SurveillanceGlobe() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId;
    let width = 0;
    let height = 0;

    // Generate static point distribution on sphere
    const points = [];
    const stepLat = 3.2;
    const stepLon = 3.6;

    for (let lat = -82; lat <= 82; lat += stepLat) {
      const phi = (90 - lat) * (Math.PI / 180);
      const radiusAtLat = Math.sin(phi);
      // Adjust longitude step to maintain uniform density across latitudes
      const lonStepAdjusted = radiusAtLat > 0.05 ? stepLon / radiusAtLat : 360;

      for (let lon = -180; lon < 180; lon += lonStepAdjusted) {
        const theta = (lon + 180) * (Math.PI / 180);
        const land = isLand(lat, lon);

        // Density modulation: high density on continents, sparse on oceans/space
        const keep = land ? Math.random() < 0.88 : Math.random() < 0.08;
        if (!keep) continue;

        // Spherical coordinates
        const x = Math.sin(phi) * Math.cos(theta);
        const y = Math.cos(phi);
        const z = Math.sin(phi) * Math.sin(theta);

        points.push({
          x,
          y,
          z,
          land,
          scatter: Math.random() > 0.94 ? 1 + (Math.random() - 0.5) * 0.12 : 1,
        });
      }
    }

    let rotY = 0.8;
    const rotX = 0.28; // Slight tilt towards viewer

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
    };

    resize();
    window.addEventListener('resize', resize);

    const render = () => {
      rotY += 0.0028; // Smooth slow rotation
      ctx.clearRect(0, 0, width, height);

      // Globe center positioned towards the right side like Cloudflare Connect
      const cx = width * 0.72;
      const cy = height * 0.52;
      const radius = Math.min(width, height) * 0.58;

      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);
      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);

      // Sort points roughly by depth for clean rendering
      for (let i = 0; i < points.length; i++) {
        const p = points[i];

        // Rotate around Y
        const x1 = (p.x * cosY - p.z * sinY) * p.scatter;
        const z1 = (p.z * cosY + p.x * sinY) * p.scatter;

        // Tilt around X
        const y2 = x1 * 0 + p.y * cosX - z1 * sinX;
        const z2 = p.y * sinX + z1 * cosX;
        const x2 = x1;

        // Hide points on far back of sphere
        if (z2 < -0.22) continue;

        const depth = (z2 + 1) / 2; // 0 to 1
        const scale = radius;
        const sx = cx + x2 * scale;
        const sy = cy - y2 * scale;

        // Size: little square pixels like Cloudflare
        const baseSize = p.land ? 2.8 : 1.8;
        const size = baseSize * (0.6 + depth * 0.7);

        // Alpha & Color based on depth
        const alpha = Math.min(1, Math.max(0.1, depth * depth * 1.3));

        if (depth > 0.6) {
          ctx.fillStyle = `rgba(255, 248, 238, ${Math.min(1, alpha + 0.22).toFixed(2)})`; // Luminous champagne cream
        } else if (depth > 0.35) {
          ctx.fillStyle = `rgba(224, 181, 121, ${alpha.toFixed(2)})`; // Warm Helios bronze-hi
        } else {
          ctx.fillStyle = `rgba(181, 115, 46, ${(alpha * 0.7).toFixed(2)})`; // Rich copper/bronze
        }

        // Draw square dot
        ctx.fillRect(sx - size / 2, sy - size / 2, size, size);
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 2,
      }}
    />
  );
}
