---
name: threejs-development
description: Build Three.js scenes that load fast and run smoothly—scene graph design, asset pipeline, lighting and materials, controls, and disposal of GPU resources.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Three.js Development

## 1. Purpose

Create interactive 3D on the web that performs on real devices. Three.js is a scene-graph and renderer library, not a game engine; many production problems come from asset weight, per-frame allocation, and undisposed GPU resources rather than shader complexity. This skill covers scene setup, the asset pipeline (glTF, compression, LOD), lighting/materials choices, camera and controls, responsive rendering, and lifecycle cleanup.

**Scope:** your own project. 3D assets are often third-party with licensing conditions—record provenance and license for every model and texture.

## 2. Activation Conditions

- Product visualization, configurators, hero scenes, or data-driven 3D.
- Scene loads slowly, drains battery, or crashes mobile GPUs.
- Memory grows over time or the tab becomes unresponsive.
- Need to integrate 3D into a React app.
- Keywords: Three.js, WebGL, scene graph, glTF, GLTFLoader, OrbitControls, raycasting, InstancedMesh, LOD, draw calls, renderer.dispose, react-three-fiber.

## 3. When Not to Use

- Simple 2D motion or images would communicate the same thing faster.
- Heavy simulation/engine features (physics, animation state machines) that need a game engine.
- Devices with no WebGL and no fallback plan.

## 4. Required Context

1. Device targets: mobile share, GPU class, WebGL2 support.
2. Scene complexity: object count, triangle budget, texture sizes, animation.
3. Interaction requirements: orbit, hover/select, drag, camera transitions.
4. Design assets available (glTF/GLB, textures, HDR environment).
5. Framework (vanilla, React) and rendering constraints (SSR).

## 5. Operating Procedure

1. **Set a performance budget first**: target 60 fps on mid-tier mobile; ≤ 100 draw calls; ≤ 300k triangles; textures ≤ 2048² for hero assets (1024² for mobile).
2. **Design the scene graph** with clear roots: static environment, dynamic objects, UI overlay; name nodes for debugging.
3. **Build the renderer correctly**: `WebGLRenderer({antialias: true, powerPreference: "high-performance"})`, cap pixel ratio at 2, handle resize with `ResizeObserver`, and pause rendering when the tab is hidden or the canvas is off-screen (`IntersectionObserver`).
4. **Use glTF as the asset format** with Draco or Meshopt compression and KTX2/Basis textures; load with a manager to track progress and errors.
5. **Choose lighting deliberately**: an HDR environment map (PMREM-generated) for PBR realism plus a directional light for shadows; limit shadow map size (1024/2048) and shadow casters.
6. **Use `InstancedMesh`** for repeated geometry (thousands of objects) instead of separate meshes.
7. **Add LOD** (`LOD`) for large scenes and frustum culling (default) with well-defined bounding volumes.
8. **Implement interaction with raycasting**, throttled to pointer events, and use `pointerdown/up` distinction to avoid click-on-drag misfires.
9. **Animate with the clock**: `renderer.setAnimationLoop` (not `requestAnimationFrame` recursively), delta-time based, no allocations inside the loop.
10. **Dispose everything on unmount**: geometries, materials, textures, render targets, and the renderer (`renderer.dispose()`, `forceContextLoss()` if needed).
11. **Provide a fallback**: a static poster image when WebGL is unavailable or fails to initialize.
12. **Measure** with `renderer.info` (draw calls, triangles, textures, geometries) and Chrome's GPU profiling.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Renderer | three.js (WebGL2); WebGPU renderer for cutting edge |
| Loaders | `GLTFLoader`, `DRACOLoader`, `KTX2Loader`, `RGBELoader` |
| Controls | `OrbitControls`, `PointerLockControls` |
| React | `@react-three/fiber`, `@react-three/drei` |
| Optimization | gltf-transform CLI, `gltfpack`, texture compression (Basis/KTX2) |
| Debug | `three` Inspector extension, Spector.js, `renderer.info`, Chrome Performance |
| Post-processing | `EffectComposer` (cost: extra passes) |

## 7. Practical Implementation

**Renderer and resize handling:**

```ts
import * as THREE from "three";

const canvas = document.querySelector<HTMLCanvasElement>("#scene")!;
const renderer = new THREE.WebGLRenderer({canvas, antialias: true, powerPreference: "high-performance"});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
camera.position.set(0, 1.6, 4);

const resize = new ResizeObserver(() => {
  const {clientWidth: w, clientHeight: h} = canvas;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
});
resize.observe(canvas);
```

**Asset loading with progress and compression:**

```ts
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
import {DRACOLoader} from "three/addons/loaders/DRACOLoader.js";
import {KTX2Loader} from "three/addons/loaders/KTX2Loader.js";

const manager = new THREE.LoadingManager();
manager.onProgress = (_url, loaded, total) => setProgress(loaded / total);
manager.onError = (url) => console.error("asset failed:", url);

const draco = new DRACOLoader().setDecoderPath("/draco/");
const ktx2 = new KTX2Loader().setTranscoderPath("/basis/").detectSupport(renderer);

const gltf = await new GLTFLoader(manager)
  .setDRACOLoader(draco)
  .setKTX2Loader(ktx2)
  .loadAsync("/assets/configurator.glb");

scene.add(gltf.scene);
gltf.scene.traverse((o) => {
  if (o instanceof THREE.Mesh) { o.castShadow = true; o.receiveShadow = true; }
});
```

**HDR environment + modest shadows:**

```ts
import {RGBELoader} from "three/addons/loaders/RGBELoader.js";

const hdr = await new RGBELoader().loadAsync("/assets/studio_1k.hdr");
hdr.mapping = THREE.EquirectangularReflectionMapping;
scene.environment = hdr;

const sun = new THREE.DirectionalLight(0xffffff, 2.0);
sun.position.set(4, 8, 4);
sun.castShadow = true;
sun.shadow.mapSize.set(1024, 1024);
sun.shadow.camera.near = 1;
sun.shadow.camera.far = 20;
scene.add(sun);
```

**InstancedMesh for repeated objects:**

```ts
const count = 2000;
const geo = new THREE.BoxGeometry(0.1, 0.1, 0.1);
const mat = new THREE.MeshStandardMaterial({color: 0x3b82f6});
const mesh = new THREE.InstancedMesh(geo, mat, count);
mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

const m = new THREE.Matrix4();
for (let i = 0; i < count; i++) {
  m.setPosition((Math.random() - 0.5) * 10, Math.random() * 2, (Math.random() - 0.5) * 10);
  mesh.setMatrixAt(i, m);
}
mesh.instanceMatrix.needsUpdate = true;
scene.add(mesh);
```

**Raycast selection without click-on-drag:**

```ts
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let downAt = {x: 0, y: 0};

canvas.addEventListener("pointerdown", (e) => { downAt = {x: e.clientX, y: e.clientY}; });
canvas.addEventListener("pointerup", (e) => {
  if (Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 4) return;  // drag, not click
  const rect = canvas.getBoundingClientRect();
  pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1,
              -((e.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const [hit] = raycaster.intersectObjects(gltf.scene.children, true);
  if (hit) onSelect(hit.object);
});
```

**Render loop with visibility pause and delta time:**

```ts
const clock = new THREE.Clock();
let running = true;

new IntersectionObserver(([entry]) => { running = entry.isIntersecting; })
  .observe(canvas);
document.addEventListener("visibilitychange", () => { running = !document.hidden; });

renderer.setAnimationLoop(() => {
  if (!running) return;
  const dt = Math.min(clock.getDelta(), 0.1);   // clamp after tab switch
  update(dt);
  renderer.render(scene, camera);
});
```

**Full disposal:**

```ts
function disposeScene(root: THREE.Object3D) {
  root.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      o.geometry?.dispose();
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) {
        for (const key of Object.keys(m)) {
          const v = (m as unknown as Record<string, unknown>)[key];
          if (v instanceof THREE.Texture) v.dispose();
        }
        m.dispose();
      }
    }
  });
}

function teardown() {
  renderer.setAnimationLoop(null);
  disposeScene(scene);
  scene.environment?.dispose();
  resize.disconnect();
  renderer.dispose();
  renderer.forceContextLoss();
}
```

**Budget check in dev:**

```ts
console.info("draw calls", renderer.info.render.calls,
             "triangles", renderer.info.render.triangles,
             "geometries", renderer.info.memory.geometries,
             "textures", renderer.info.memory.textures);
```

**Asset optimization CLI (gltf-transform):**

```bash
npx @gltf-transform/cli optimize in.glb out.glb \
  --compress draco --texture-compress webp --texture-size 2048
npx @gltf-transform/cli inspect out.glb
```

## 8. Quality Standards

- Draw calls, triangles, and texture memory are within the stated budget on target devices.
- Rendering pauses when off-screen or hidden; no runaway battery drain.
- Assets use glTF + Draco/Meshopt + KTX2 and are preloaded with progress UI.
- No per-frame allocations in the render loop (reuse vectors/matrices).
- Everything is disposed on unmount; repeated mount/unmount does not grow memory.
- WebGL failure produces a static fallback, not a blank canvas.
- Mobile: capped pixel ratio and reduced shadow/texture settings.

## 9. Verification and Testing

- Chrome Performance profile: steady 16 ms frames during interaction on 4× CPU throttle.
- `renderer.info` snapshot in CI-like dev check against budgets.
- Memory test: mount/unmount 20 times, confirm no growth in the memory panel.
- Visual regression on a fixed camera pose with deterministic lighting.
- Mobile device test (real hardware) for load time and thermal throttling.
- Fallback test: disable WebGL (`chrome://flags`) and confirm the poster renders.

## 10. Security Considerations

- glTF can embed external URIs and scripts in extensions; load assets from your own origin and validate/sanitize models.
- Cross-origin textures without CORS break WebGL and may leak referrers; host assets yourself.
- Never render untrusted shader code; treat custom GLSL as executable content.
- Canvas readback (`toDataURL`, `readPixels`) of sensitive content can be blocked; do not rely on Canvas for confidentiality.
- GPU drivers and browser versions vary; a crash can take down the tab—guard long-running work with budgets.
- 3D assets frequently carry licensing terms (editorial vs. commercial); record them.

## 11. Failure Handling

- **Black canvas:** check the camera position/near-far, light presence, and shader compile errors in the console.
- **Everything is dark:** no environment or lights, or materials expecting an env map (`MeshStandardMaterial` with `metalness: 1` needs `scene.environment`).
- **Mobile crash:** reduce texture sizes, drop shadow map resolution, cap pixel ratio, and lower instance counts.
- **Stutter on first frames:** shader compilation—use `renderer.compile(scene, camera)` before revealing the canvas or show a loading state.
- **Memory growth:** missing disposal; audit texture creation and render targets.
- **Click selects nothing:** raycast against the correct root and ensure `matrixWorld` is updated (raycaster needs updated matrices after transforms).

## 12. Expected Deliverables

1. Scene structure and performance budget.
2. Renderer setup with resize/visibility handling.
3. Asset pipeline (compression, sizes, provenance/licenses).
4. Interaction implementation (controls, picking).
5. Disposal/teardown code.
6. Performance measurements and device test notes.
7. Fallback strategy.

## 13. References

- Three.js documentation — https://threejs.org/docs/
- Three.js manual — https://threejs.org/manual/
- glTF 2.0 specification — https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- gltf-transform — https://gltf-transform.dev/
- react-three-fiber — https://r3f.docs.pmnd.rs/
- MDN WebGL best practices — https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices
- Khronos KTX2 / Basis Universal — https://github.com/KhronosGroup/KTX-Software
