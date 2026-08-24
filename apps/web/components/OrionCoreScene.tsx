"use client";

// ORION CORE — 3D particle visual for the Command Center (P41/P42).
// A trunk-to-canopy particle cloud (three.js/WebGL):
//   - a tight always-on green cluster at the center — "the head" — pulses
//     gently regardless of market data, representing ORION itself being alive.
//   - the surrounding canopy is split into angular sectors, one per tracked
//     asset, each tinted that asset's own color and its radius/turbulence
//     scaled by that asset's REAL relative volume (from the scanner /
//     command ticker — 0 when no reading exists yet, never fabricated).
// Geometry is built once on mount from the initial `assets` list (identity —
// symbol/color — is stable for the component's lifetime); only each asset's
// `intensity` is re-read every frame via a ref, so updates from polling never
// trigger a geometry rebuild.

import { useEffect, useRef } from "react";
import * as THREE from "three";

export type OrionAssetVolume = {
  symbol: string;
  /** hex color, e.g. 0xe930ff */
  color: number;
  /** 0..1, normalized real relative volume. 0 = no data yet / calm. */
  intensity: number;
};

export type OrionCoreSceneProps = {
  thinking: boolean;
  activeCount: number;
  totalCount: number;
  assets: OrionAssetVolume[];
};

const PARTICLE_COUNT = 6600;
const CORE_FRACTION = 0.14;
const CORE_HEX = 0x6cffa8; // ORION's own color — the "head", always on

/** Tight cluster near the origin — the always-active core. */
function sampleCorePosition(): [number, number, number, number] {
  const r = Math.pow(Math.random(), 1.5) * 0.32;
  const angle = Math.random() * Math.PI * 2;
  const y = (Math.random() - 0.5) * 0.45;
  const phase = Math.random() * Math.PI * 2;
  return [Math.cos(angle) * r, y, Math.sin(angle) * r, phase];
}

/** Trunk (narrow) -> waist (pinch) -> canopy (wide), confined to one angular sector. */
function sampleStrandPosition(sectorStart: number, sectorWidth: number): [number, number, number, number] {
  const t = Math.random();
  const y = -1.55 + t * 3.1;
  let radius: number;
  if (t < 0.4) {
    radius = 0.12 + 0.35 * Math.pow(t / 0.4, 1.6);
  } else if (t < 0.55) {
    const local = (t - 0.4) / 0.15;
    radius = 0.4 - 0.16 * Math.sin(local * Math.PI);
  } else {
    const local = (t - 0.55) / 0.45;
    radius = 0.3 + local * 1.5 + (Math.random() - 0.5) * 0.5 * local;
  }
  const angle = sectorStart + Math.random() * sectorWidth;
  const rx = radius * (0.75 + Math.random() * 0.5);
  const rz = radius * (0.65 + Math.random() * 0.4);
  const phase = Math.random() * Math.PI * 2;
  return [Math.cos(angle) * rx, y, Math.sin(angle) * rz, phase];
}

export default function OrionCoreScene(props: OrionCoreSceneProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let width = mount.clientWidth || 1;
    let height = mount.clientHeight || 1;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 20);
    camera.position.set(0, 0.15, 4.3);
    camera.lookAt(0, 0.1, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    mount.appendChild(renderer.domElement);

    const initialAssets = propsRef.current.assets.length > 0 ? propsRef.current.assets : [
      { symbol: "—", color: CORE_HEX, intensity: 0 },
    ];
    const nAssets = initialAssets.length;
    const sectorWidth = (Math.PI * 2) / nAssets;
    const coreCount = Math.round(PARTICLE_COUNT * CORE_FRACTION);
    const perAsset = Math.floor((PARTICLE_COUNT - coreCount) / nAssets);

    const basePositions = new Float32Array(PARTICLE_COUNT * 3);
    const drawPositions = new Float32Array(PARTICLE_COUNT * 3);
    const phases = new Float32Array(PARTICLE_COUNT);
    const seeds = new Float32Array(PARTICLE_COUNT);
    const colors = new Float32Array(PARTICLE_COUNT * 3);
    // -1 = always-on core particle; >=0 = index into `assets`
    const assetIndexOf = new Int16Array(PARTICLE_COUNT).fill(-1);

    let cursor = 0;
    const writeParticle = (x: number, y: number, z: number, phase: number, colorHex: number, assetIdx: number) => {
      basePositions[cursor * 3] = x;
      basePositions[cursor * 3 + 1] = y;
      basePositions[cursor * 3 + 2] = z;
      drawPositions[cursor * 3] = x;
      drawPositions[cursor * 3 + 1] = y;
      drawPositions[cursor * 3 + 2] = z;
      phases[cursor] = phase;
      seeds[cursor] = Math.random();
      const c = new THREE.Color(colorHex);
      colors[cursor * 3] = c.r;
      colors[cursor * 3 + 1] = c.g;
      colors[cursor * 3 + 2] = c.b;
      assetIndexOf[cursor] = assetIdx;
      cursor++;
    };

    for (let i = 0; i < coreCount; i++) {
      const [x, y, z, phase] = sampleCorePosition();
      writeParticle(x, y, z, phase, CORE_HEX, -1);
    }
    for (let a = 0; a < nAssets; a++) {
      const sectorStart = a * sectorWidth;
      const count = a === nAssets - 1 ? PARTICLE_COUNT - cursor : perAsset;
      const color = initialAssets[a].color;
      for (let i = 0; i < count; i++) {
        const [x, y, z, phase] = sampleStrandPosition(sectorStart, sectorWidth);
        writeParticle(x, y, z, phase, color, a);
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(drawPositions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: 0.022,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);

    // ambient core glow — a soft sprite behind the particle cloud, always the core color
    const glowTex = (() => {
      const size = 128;
      const canvas = document.createElement("canvas");
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        grad.addColorStop(0, "rgba(108,255,168,0.35)");
        grad.addColorStop(1, "rgba(108,255,168,0)");
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, size, size);
      }
      return new THREE.CanvasTexture(canvas);
    })();
    const glowMaterial = new THREE.SpriteMaterial({
      map: glowTex,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const glow = new THREE.Sprite(glowMaterial);
    glow.scale.set(2.6, 2.6, 1);
    glow.position.set(0, 0, -0.4);
    scene.add(glow);

    const resize = () => {
      width = mount.clientWidth || 1;
      height = mount.clientHeight || 1;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    let raf = 0;
    let lastNow = 0;

    const animate = (now: number) => {
      raf = requestAnimationFrame(animate);
      const dt = Math.min(0.05, lastNow === 0 ? 0.016 : (now - lastNow) / 1000);
      lastNow = now;

      const { thinking, activeCount, totalCount, assets } = propsRef.current;
      const activity = totalCount > 0 ? activeCount / totalCount : 0;
      const spinSpeed = 0.05 + activity * 0.1 + (thinking ? 0.16 : 0);
      points.rotation.y += dt * spinSpeed;

      const pos = geometry.attributes.position as THREE.BufferAttribute;
      const t = now / 1000;
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const bx = basePositions[i * 3];
        const by = basePositions[i * 3 + 1];
        const bz = basePositions[i * 3 + 2];
        const ph = phases[i];
        const ai = assetIndexOf[i];
        if (ai === -1) {
          const pulse = 1 + Math.sin(t * 1.2 + ph) * 0.15 + (thinking ? 0.08 : 0);
          pos.array[i * 3] = bx * pulse;
          pos.array[i * 3 + 1] = by;
          pos.array[i * 3 + 2] = bz * pulse;
        } else {
          const intensity = assets[ai]?.intensity ?? 0;
          const outward = 1 + intensity * 0.95;
          const turbulence = 0.02 + intensity * 0.14 + (thinking ? 0.04 : 0);
          const wobble = Math.sin(t * (0.6 + seeds[i] * 0.8) + ph) * turbulence;
          pos.array[i * 3] = bx * outward + wobble * (0.4 + seeds[i]);
          pos.array[i * 3 + 1] = by + Math.cos(t * (0.5 + seeds[i] * 0.6) + ph) * turbulence * 0.6;
          pos.array[i * 3 + 2] = bz * outward + wobble * (0.3 + seeds[i] * 0.5);
        }
      }
      pos.needsUpdate = true;

      material.size = 0.018 + activity * 0.01 + (thinking ? 0.005 : 0);
      material.opacity = 0.72 + activity * 0.18;
      glowMaterial.opacity = 0.55 + activity * 0.35 + (thinking ? 0.1 : 0);

      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      mount.removeChild(renderer.domElement);
      geometry.dispose();
      material.dispose();
      glowTex.dispose();
      glowMaterial.dispose();
      renderer.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={mountRef} className="absolute inset-0" aria-hidden="true" />;
}
