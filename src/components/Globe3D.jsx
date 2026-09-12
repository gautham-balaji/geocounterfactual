import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { MapPin, Navigation, Compass } from 'lucide-react';

export default function Globe3D({ regions, selectedRegionId, onSelectRegion }) {
  const mountRef = useRef(null);
  const [hoveredRegion, setHoveredRegion] = useState(null);
  const [isRotating, setIsRotating] = useState(true);

  useEffect(() => {
    const currentMount = mountRef.current;
    if (!currentMount) return;

    const width = currentMount.clientWidth;
    const height = currentMount.clientHeight;

    // Scene, Camera, Renderer
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 240;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    currentMount.appendChild(renderer.domElement);

    // Globe Base Group
    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    // 1. Globe Sphere (Dark Space Ocean)
    const sphereGeometry = new THREE.SphereGeometry(75, 64, 64);
    const sphereMaterial = new THREE.MeshPhongMaterial({
      color: 0x091122,
      emissive: 0x040814,
      shininess: 25,
      specular: 0x1e3a8a,
      transparent: true,
      opacity: 0.95
    });
    const globeMesh = new THREE.Mesh(sphereGeometry, sphereMaterial);
    globeGroup.add(globeMesh);

    // 2. Wireframe / Latitude Longitude Lines
    const wireframeGeometry = new THREE.WireframeGeometry(new THREE.SphereGeometry(75.5, 24, 24));
    const wireframeMaterial = new THREE.LineBasicMaterial({
      color: 0x1e293b,
      transparent: true,
      opacity: 0.35
    });
    const wireframeMesh = new THREE.LineSegments(wireframeGeometry, wireframeMaterial);
    globeGroup.add(wireframeMesh);

    // 3. Atmospheric Outer Glow Ring
    const atmosphereGeometry = new THREE.SphereGeometry(79, 64, 64);
    const atmosphereMaterial = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormal;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec3 vNormal;
        void main() {
          float intensity = pow(0.6 - dot(vNormal, vec3(0, 0, 1.0)), 2.5);
          gl_FragColor = vec4(0.02, 0.71, 0.83, 1.0) * intensity;
        }
      `,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true
    });
    const atmosphereMesh = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    scene.add(atmosphereMesh);

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x06b6d4, 1.5);
    dirLight1.position.set(200, 200, 200);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x10b981, 0.8);
    dirLight2.position.set(-200, -100, -100);
    scene.add(dirLight2);

    // Convert Lat/Lng to 3D Coordinates
    const latLngToVector3 = (lat, lng, radius) => {
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lng + 180) * (Math.PI / 180);
      const x = -(radius * Math.sin(phi) * Math.cos(theta));
      const z = radius * Math.sin(phi) * Math.sin(theta);
      const y = radius * Math.cos(phi);
      return new THREE.Vector3(x, y, z);
    };

    // 5. Region Markers
    const markerGroup = new THREE.Group();
    globeGroup.add(markerGroup);

    const markerMeshes = [];

    regions.forEach((region) => {
      const pos = latLngToVector3(region.lat, region.lng, 76.5);
      const isSelected = region.id === selectedRegionId;

      // Glowing dot mesh
      const dotGeo = new THREE.SphereGeometry(isSelected ? 2.8 : 2.0, 16, 16);
      const dotMat = new THREE.MeshBasicMaterial({
        color: isSelected ? 0x10b981 : 0x06b6d4
      });
      const dotMesh = new THREE.Mesh(dotGeo, dotMat);
      dotMesh.position.copy(pos);
      dotMesh.userData = { region };
      markerGroup.add(dotMesh);
      markerMeshes.push(dotMesh);

      // Pulsing outer ring
      const ringGeo = new THREE.RingGeometry(2.5, 4.2, 32);
      const ringMat = new THREE.MeshBasicMaterial({
        color: isSelected ? 0x10b981 : 0x06b6d4,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: isSelected ? 0.9 : 0.5
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.position.copy(pos.clone().multiplyScalar(1.01));
      ringMesh.lookAt(new THREE.Vector3(0, 0, 0));
      markerGroup.add(ringMesh);

      // Small vertical beam
      const lineMat = new THREE.LineBasicMaterial({ color: isSelected ? 0x10b981 : 0x06b6d4, transparent: true, opacity: 0.8 });
      const lineGeo = new THREE.BufferGeometry().setFromPoints([
        pos,
        pos.clone().multiplyScalar(1.08)
      ]);
      const lineMesh = new THREE.Line(lineGeo, lineMat);
      markerGroup.add(lineMesh);
    });

    // Rotate globe to center on India by default
    // India coordinates approx lat 20, lng 78
    const targetVector = latLngToVector3(20, 78, 1);
    globeGroup.rotation.y = -Math.atan2(targetVector.z, targetVector.x) + Math.PI / 2;
    globeGroup.rotation.x = 0.35;

    // Mouse Interaction (Raycasting & Dragging)
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    let isMouseDown = false;
    let previousMousePosition = { x: 0, y: 0 };

    const handleMouseDown = (e) => {
      isMouseDown = true;
      previousMousePosition = { x: e.clientX, y: e.clientY };
    };

    const handleMouseMove = (e) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      // Raycast marker detection
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(markerMeshes);

      if (intersects.length > 0) {
        const region = intersects[0].object.userData.region;
        setHoveredRegion(region);
        renderer.domElement.style.cursor = 'pointer';
      } else {
        setHoveredRegion(null);
        renderer.domElement.style.cursor = isMouseDown ? 'grabbing' : 'grab';
      }

      if (isMouseDown) {
        const deltaX = e.clientX - previousMousePosition.x;
        const deltaY = e.clientY - previousMousePosition.y;

        globeGroup.rotation.y += deltaX * 0.005;
        globeGroup.rotation.x += deltaY * 0.005;

        previousMousePosition = { x: e.clientX, y: e.clientY };
      }
    };

    const handleMouseUp = () => {
      isMouseDown = false;
    };

    const handleClick = () => {
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(markerMeshes);

      if (intersects.length > 0) {
        const region = intersects[0].object.userData.region;
        onSelectRegion(region.id);
      }
    };

    const domElement = renderer.domElement;
    domElement.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    domElement.addEventListener('click', handleClick);

    // Animation Loop
    let animationFrameId;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);

      if (isRotating && !isMouseDown) {
        globeGroup.rotation.y += 0.002;
      }

      // Animate pulsing rings
      markerGroup.children.forEach((child) => {
        if (child.type === 'Mesh' && child.geometry.type === 'RingGeometry') {
          child.scale.x = 1 + Math.sin(Date.now() * 0.004) * 0.15;
          child.scale.y = 1 + Math.sin(Date.now() * 0.004) * 0.15;
        }
      });

      renderer.render(scene, camera);
    };

    animate();

    // Resize Handler
    const handleResize = () => {
      if (!currentMount) return;
      const newWidth = currentMount.clientWidth;
      const newHeight = currentMount.clientHeight;
      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      domElement.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      domElement.removeEventListener('click', handleClick);
      window.removeEventListener('resize', handleResize);
      if (currentMount.contains(renderer.domElement)) {
        currentMount.removeChild(renderer.domElement);
      }
    };
  }, [regions, selectedRegionId, onSelectRegion, isRotating]);

  const selectedRegion = regions.find(r => r.id === selectedRegionId);

  return (
    <div className="relative w-full h-[420px] rounded-2xl overflow-hidden glass-panel border border-slate-800/80 shadow-2xl flex flex-col justify-between">
      {/* 3D Canvas Target */}
      <div ref={mountRef} className="absolute inset-0 z-0 cursor-grab active:cursor-grabbing" />

      {/* Top Overlay HUD */}
      <div className="relative z-10 p-4 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-2 bg-darkbg-900/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-700/60 pointer-events-auto">
          <Compass className="w-4 h-4 text-cyan-400 animate-spin-slow" />
          <span className="text-xs font-mono font-medium text-slate-300">INTERACTIVE 3D GLOBE</span>
        </div>

        <button
          onClick={() => setIsRotating(!isRotating)}
          className="pointer-events-auto bg-darkbg-900/80 hover:bg-slate-800/80 text-xs font-mono px-3 py-1.5 rounded-lg border border-slate-700/60 text-slate-300 transition flex items-center gap-1.5"
        >
          <span className={`w-2 h-2 rounded-full ${isRotating ? 'bg-emerald-400 animate-ping-slow' : 'bg-slate-500'}`} />
          {isRotating ? 'Auto-Rotation ON' : 'Paused'}
        </button>
      </div>

      {/* Hover / Active Marker Tooltip HUD */}
      <div className="relative z-10 p-4 flex flex-col justify-end pointer-events-none">
        {hoveredRegion ? (
          <div className="bg-darkbg-900/90 backdrop-blur-md p-3 rounded-xl border border-cyan-500/50 shadow-glow-cyan pointer-events-auto transition-all transform animate-fadeIn">
            <div className="flex items-center gap-2 text-cyan-400 text-xs font-mono font-semibold">
              <MapPin className="w-3.5 h-3.5" />
              <span>REGION PIN DETECTED</span>
            </div>
            <div className="text-sm font-bold text-white mt-1">{hoveredRegion.name}</div>
            <div className="text-xs text-slate-400">{hoveredRegion.state} • {hoveredRegion.climateZone}</div>
            <div className="text-[11px] text-cyan-300 mt-2 font-mono">Click to target this region in simulator →</div>
          </div>
        ) : selectedRegion ? (
          <div className="bg-darkbg-900/80 backdrop-blur-md p-3 rounded-xl border border-emerald-500/40 pointer-events-auto">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-emerald-400 flex items-center gap-1">
                <Navigation className="w-3.5 h-3.5" /> ACTIVE TARGET
              </span>
              <span className="text-slate-400">{selectedRegion.lat}°N, {selectedRegion.lng}°E</span>
            </div>
            <div className="text-sm font-semibold text-slate-100 mt-0.5">{selectedRegion.name}</div>
            <div className="text-xs text-slate-400">{selectedRegion.state}</div>
          </div>
        ) : null}
      </div>

      {/* Region Selection Pills at Bottom */}
      <div className="relative z-10 p-3 bg-darkbg-900/80 backdrop-blur-md border-t border-slate-800 flex items-center gap-2 overflow-x-auto">
        <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider shrink-0 mr-1">Select Zone:</span>
        {regions.map((reg) => {
          const isSelected = reg.id === selectedRegionId;
          return (
            <button
              key={reg.id}
              onClick={() => onSelectRegion(reg.id)}
              className={`shrink-0 text-xs px-3 py-1.5 rounded-lg font-mono font-medium transition flex items-center gap-1.5 ${
                isSelected
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/60 shadow-glow-emerald'
                  : 'bg-slate-800/60 text-slate-300 hover:bg-slate-700/80 border border-slate-700/50'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-emerald-400' : 'bg-slate-500'}`} />
              {reg.name.split(' ')[0]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
