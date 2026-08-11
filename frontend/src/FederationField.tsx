import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import type { HubSource } from './types';

function hashHue(value: string): number {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) hash = Math.imul(hash ^ value.charCodeAt(i), 16777619);
  return Math.abs(hash) % 360;
}

function glowTexture(inner: string, middle: string): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 256; canvas.height = 256;
  const context = canvas.getContext('2d')!;
  const gradient = context.createRadialGradient(128, 128, 0, 128, 128, 128);
  gradient.addColorStop(0, inner);
  gradient.addColorStop(.14, middle);
  gradient.addColorStop(.48, 'rgba(26,86,160,.18)');
  gradient.addColorStop(1, 'rgba(0,0,0,0)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, 256, 256);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export default function FederationField({ sources }: { sources: HubSource[] }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const compact = window.innerWidth < 720;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x03040a, .048);
    const camera = new THREE.PerspectiveCamera(43, 1, .1, 80);
    camera.position.set(0, .4, compact ? 12.8 : 11.2);
    camera.lookAt(0, 0, 0);
    const renderer = new THREE.WebGLRenderer({ antialias: !compact, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, compact ? 1.5 : 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.38;
    renderer.domElement.style.touchAction = 'none';
    element.appendChild(renderer.domElement);

    const world = new THREE.Group();
    scene.add(world);
    scene.add(new THREE.AmbientLight(0x304068, 1.25));
    const cyanLight = new THREE.PointLight(0x35e7ff, 44, 28, 1.4);
    cyanLight.position.set(2.8, 3.4, 4.5);
    scene.add(cyanLight);
    const violetLight = new THREE.PointLight(0x8e63ff, 32, 24, 1.5);
    violetLight.position.set(-4.5, -2.2, 2);
    scene.add(violetLight);
    const roseLight = new THREE.PointLight(0xff4ecd, 20, 18, 1.5);
    roseLight.position.set(4.2, -2.7, -1);
    scene.add(roseLight);

    const cyanGlow = glowTexture('rgba(255,255,255,1)', 'rgba(38,236,255,.86)');
    const violetGlow = glowTexture('rgba(255,255,255,.92)', 'rgba(148,92,255,.72)');
    const roseGlow = glowTexture('rgba(255,255,255,.9)', 'rgba(255,70,200,.7)');
    const textures = [cyanGlow, violetGlow, roseGlow];

    const nebulae = [
      [-5.2, 2.6, -6, 7.5, violetGlow, .26],
      [5.4, -2.8, -7, 8.5, roseGlow, .2],
      [.4, .2, -8, 10, cyanGlow, .13],
    ] as const;
    nebulae.forEach(([x, y, z, scale, map, opacity]) => {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map, color: 0xffffff, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false }));
      sprite.position.set(x, y, z); sprite.scale.set(scale, scale, 1); scene.add(sprite);
    });

    const core = new THREE.Group();
    world.add(core);
    const coreBody = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.16, 4),
      new THREE.MeshStandardMaterial({ color: 0x075b86, emissive: 0x0acfee, emissiveIntensity: 1.8, roughness: .22, metalness: .38, transparent: true, opacity: .82 }),
    );
    core.add(coreBody);
    const coreWire = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.35, 2),
      new THREE.MeshBasicMaterial({ color: 0x86f8ff, wireframe: true, transparent: true, opacity: .68, blending: THREE.AdditiveBlending }),
    );
    core.add(coreWire);
    const innerWire = new THREE.Mesh(
      new THREE.OctahedronGeometry(.72, 2),
      new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true, transparent: true, opacity: .48 }),
    );
    core.add(innerWire);
    const coreAura = new THREE.Sprite(new THREE.SpriteMaterial({ map: cyanGlow, transparent: true, opacity: .78, blending: THREE.AdditiveBlending, depthWrite: false }));
    coreAura.scale.set(5.2, 5.2, 1); core.add(coreAura);

    const orbitalRings: THREE.Mesh[] = [];
    [1.75, 2.45, 3.25, 4.05].forEach((radius, index) => {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(radius, index === 0 ? .014 : .008, 6, 180),
        new THREE.MeshBasicMaterial({ color: index % 2 ? 0x9b6dff : 0x41eaff, transparent: true, opacity: .22 + index * .035, blending: THREE.AdditiveBlending }),
      );
      ring.rotation.set(.62 + index * .34, .22 + index * .27, index * .73);
      orbitalRings.push(ring); world.add(ring);
    });

    const starCount = compact ? 900 : 1900;
    const starPositions = new Float32Array(starCount * 3);
    const starColors = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i += 1) {
      const radius = 7 + ((i * 47) % 190) / 10;
      const angle = i * 2.3999632297;
      starPositions[i * 3] = Math.cos(angle) * radius;
      starPositions[i * 3 + 1] = (((i * 83) % 260) / 130 - 1) * 9;
      starPositions[i * 3 + 2] = Math.sin(angle) * radius;
      const color = new THREE.Color(i % 19 === 0 ? 0xff8bdd : i % 11 === 0 ? 0x8d72ff : 0xa6eaff);
      starColors.set([color.r, color.g, color.b], i * 3);
    }
    const starGeometry = new THREE.BufferGeometry();
    starGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    starGeometry.setAttribute('color', new THREE.BufferAttribute(starColors, 3));
    const starField = new THREE.Points(
      starGeometry,
      new THREE.PointsMaterial({ size: compact ? .024 : .032, vertexColors: true, transparent: true, opacity: .78, sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false }),
    );
    scene.add(starField);

    const dustCount = compact ? 240 : 520;
    const dust = new Float32Array(dustCount * 3);
    for (let i = 0; i < dustCount; i += 1) {
      const angle = i * 2.399963;
      const radius = 1.6 + ((i * 29) % 300) / 100;
      dust[i * 3] = Math.cos(angle) * radius;
      dust[i * 3 + 1] = Math.sin(angle) * radius * .34;
      dust[i * 3 + 2] = Math.sin(angle * 1.7) * .72;
    }
    const dustGeometry = new THREE.BufferGeometry();
    dustGeometry.setAttribute('position', new THREE.BufferAttribute(dust, 3));
    const orbitalDust = new THREE.Points(dustGeometry, new THREE.PointsMaterial({ color: 0x58eeff, size: .022, transparent: true, opacity: .5, blending: THREE.AdditiveBlending, depthWrite: false }));
    world.add(orbitalDust);

    const nodes: { group: THREE.Group; base: THREE.Vector3; phase: number; glow: THREE.Sprite }[] = [];
    const pulses: { mesh: THREE.Mesh; curve: THREE.CatmullRomCurve3; phase: number; speed: number }[] = [];
    sources.forEach((source, index) => {
      const phase = (index / Math.max(sources.length, 1)) * Math.PI * 2 + .55;
      const radius = 3.25 + (index % 3) * .58;
      const base = new THREE.Vector3(Math.cos(phase) * radius, Math.sin(phase * 1.55) * 1.58, Math.sin(phase) * radius * .5);
      const size = Math.min(.78, .22 + Math.sqrt(Math.max(1, source.capabilities)) * .062);
      const color = new THREE.Color().setHSL(hashHue(source.id) / 360, .9, .62);
      const group = new THREE.Group(); group.position.copy(base); world.add(group);
      const node = new THREE.Mesh(
        new THREE.IcosahedronGeometry(size, 2),
        new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 1.1, roughness: .25, metalness: .2 }),
      );
      group.add(node);
      const wire = new THREE.Mesh(
        new THREE.IcosahedronGeometry(size * 1.16, 1),
        new THREE.MeshBasicMaterial({ color, wireframe: true, transparent: true, opacity: .7 }),
      );
      group.add(wire);
      const halo = new THREE.Mesh(
        new THREE.TorusGeometry(size * 1.7, .018, 5, 72),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .58, blending: THREE.AdditiveBlending }),
      );
      halo.rotation.x = Math.PI / 2.8; group.add(halo);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: cyanGlow, color, transparent: true, opacity: .65, blending: THREE.AdditiveBlending, depthWrite: false }));
      glow.scale.set(size * 5.1, size * 5.1, 1); group.add(glow);
      nodes.push({ group, base, phase, glow });

      const bend = base.clone().multiplyScalar(.48);
      bend.y += index % 2 ? 1.15 : -1.15;
      bend.z += .7;
      const curve = new THREE.CatmullRomCurve3([base, bend, new THREE.Vector3()]);
      const path = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(curve.getPoints(96)),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: .28, blending: THREE.AdditiveBlending }),
      );
      world.add(path);
      for (let lane = 0; lane < 3; lane += 1) {
        const pulse = new THREE.Mesh(
          new THREE.SphereGeometry(.045 + lane * .012, 10, 10),
          new THREE.MeshBasicMaterial({ color: lane === 2 ? 0xffffff : color, blending: THREE.AdditiveBlending }),
        );
        world.add(pulse);
        pulses.push({ mesh: pulse, curve, phase: (lane / 3 + index * .17) % 1, speed: .085 + lane * .021 + index * .006 });
      }
    });

    let width = 0; let height = 0;
    const resize = () => {
      width = Math.max(1, element.clientWidth); height = Math.max(1, element.clientHeight);
      renderer.setSize(width, height, true); camera.aspect = width / height; camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize); observer.observe(element); resize();

    let targetYaw = 0; let targetPitch = 0; let pointer: { x: number; y: number } | null = null;
    const down = (event: PointerEvent) => { pointer = { x: event.clientX, y: event.clientY }; renderer.domElement.setPointerCapture(event.pointerId); };
    const move = (event: PointerEvent) => {
      if (!pointer) return;
      targetYaw += (event.clientX - pointer.x) * .006;
      targetPitch = THREE.MathUtils.clamp(targetPitch + (event.clientY - pointer.y) * .004, -.52, .52);
      pointer = { x: event.clientX, y: event.clientY };
    };
    const up = () => { pointer = null; };
    renderer.domElement.addEventListener('pointerdown', down);
    renderer.domElement.addEventListener('pointermove', move);
    renderer.domElement.addEventListener('pointerup', up);
    renderer.domElement.addEventListener('pointercancel', up);

    let frame = 0; const started = performance.now();
    const draw = () => {
      const elapsed = (performance.now() - started) / 1000;
      if (!reduced) {
        coreBody.rotation.set(elapsed * .055, elapsed * .15, elapsed * .028);
        coreWire.rotation.set(-elapsed * .038, -elapsed * .11, elapsed * .047);
        innerWire.rotation.set(elapsed * .18, -elapsed * .23, elapsed * .1);
        coreAura.material.opacity = .68 + Math.sin(elapsed * 1.8) * .11;
        coreAura.scale.setScalar(5.1 + Math.sin(elapsed * 1.4) * .22);
        orbitalRings.forEach((ring, index) => { ring.rotation.z += .0007 * (index + 1); ring.rotation.y += .00023 * (index % 2 ? -1 : 1); });
        orbitalDust.rotation.z = elapsed * .025; orbitalDust.rotation.y = -elapsed * .018;
        nodes.forEach(({ group, base, phase, glow }, index) => {
          group.position.y = base.y + Math.sin(elapsed * .68 + phase) * .16;
          group.rotation.y = elapsed * (.16 + index * .014);
          group.rotation.z = Math.sin(elapsed * .35 + phase) * .18;
          glow.material.opacity = .5 + Math.sin(elapsed * 2.1 + phase) * .18;
        });
        pulses.forEach(({ mesh, curve, phase, speed }) => {
          mesh.position.copy(curve.getPointAt((phase + elapsed * speed) % 1));
          mesh.scale.setScalar(.78 + Math.sin(elapsed * 4 + phase * 9) * .22);
        });
        starField.rotation.y = elapsed * .008; starField.rotation.x = Math.sin(elapsed * .06) * .025;
        camera.position.y = .4 + Math.sin(elapsed * .17) * .12;
      }
      world.rotation.y += (targetYaw - world.rotation.y) * .045;
      world.rotation.x += (targetPitch - world.rotation.x) * .045;
      camera.lookAt(0, 0, 0); renderer.render(scene, camera);
      frame = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(frame); observer.disconnect();
      renderer.domElement.removeEventListener('pointerdown', down);
      renderer.domElement.removeEventListener('pointermove', move);
      renderer.domElement.removeEventListener('pointerup', up);
      renderer.domElement.removeEventListener('pointercancel', up);
      scene.traverse((object) => {
        const renderable = object as THREE.Mesh | THREE.Line | THREE.Points | THREE.Sprite;
        if ('geometry' in renderable && renderable.geometry) renderable.geometry.dispose();
        if ('material' in renderable && renderable.material) {
          const materials = Array.isArray(renderable.material) ? renderable.material : [renderable.material];
          materials.forEach((material) => material.dispose());
        }
      });
      textures.forEach((texture) => texture.dispose()); renderer.dispose();
      if (renderer.domElement.parentNode === element) element.removeChild(renderer.domElement);
    };
  }, [sources]);

  return <div className="federation-field" ref={host} aria-label="Animated 3D federation constellation" />;
}
