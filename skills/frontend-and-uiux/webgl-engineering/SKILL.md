---
name: webgl-engineering
description: Engineer WebGL and shader pipelines—GLSL, buffers and VAOs, draw-call batching, precision, GPU profiling, and graceful capability detection.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# WebGL Engineering

## 1. Purpose

Work below the scene-graph level: raw WebGL/GLSL for custom visuals, post-processing, and performance-critical rendering. The dominant costs are CPU-GPU round trips, per-frame state changes, and shader complexity on weak GPUs. This skill covers context setup, GLSL correctness across drivers, buffer layout, batching, precision handling, and the profiling discipline needed to hit frame budgets on mobile.

**Scope:** your own renderers. Shaders are executable content—never compile shader source from untrusted input.

## 2. Activation Conditions

- Writing custom shaders or raw WebGL (not just Three.js scene assembly).
- Post-processing effects, image filters, compute-like passes, or data visualization.
- Frame rate collapses on mobile or integrated GPUs.
- Need to debug shader compile failures or precision artifacts.
- Keywords: WebGL2, GLSL, shader, vertex buffer, VAO, uniform, texture, framebuffer, instancing, precision, mobile GPU, render loop, context loss.

## 3. When Not to Use

- Standard 3D with models, lights, and cameras (use threejs-development — it saves months).
- Complex ML/vision pipelines (use WebGPU or WASM with a dedicated library).
- 2D graphics achievable with SVG/Canvas2D.

## 4. Required Context

1. Target browsers/devices and WebGL2 availability.
2. Effect requirements: inputs (textures, geometry), outputs, interaction.
3. Frame budget (16.7 ms at 60 fps, 33 ms at 30 fps) and resolution.
4. Precision requirements (half vs. full float, integer operations).
5. Existing renderer/framework integration constraints.

## 5. Operating Procedure

1. **Detect capability** before initializing: WebGL2 context, extensions (`EXT_color_buffer_float`, `OES_texture_float_linear`), and fall back gracefully.
2. **Set up the context once**: `canvas.getContext("webgl2", {antialias, alpha, powerPreference, preserveDrawingBuffer: false})`, cap pixel ratio, handle `webglcontextlost`/`restored`.
3. **Define a buffer layout** explicitly: interleaved attributes, typed arrays, VAOs bound per mesh.
4. **Write portable GLSL**: declare `precision mediump float;` (highp only where needed), avoid driver-specific extensions, always check `getShaderInfoLog` on compile and `getProgramInfoLog` on link.
5. **Minimize state changes**: sort draws by program/texture, batch geometry, and use instancing for repeated meshes.
6. **Keep data on the GPU**: upload once with `STATIC_DRAW`, update with `bufferSubData` for dynamic data; avoid `readPixels` in the frame loop.
7. **Render to framebuffers** for multi-pass effects with `RGBA16F` where supported, and resize render targets in the resize handler.
8. **Handle precision on mobile**: use `mediump` for color math, `highp` for positions and large coordinates, and test with `SIMD`-less GPUs.
9. **Profile with GPU timers**: `EXT_disjoint_timer_query_webgl2` (where available), Chrome GPU profiling, and frame-time graphs; find the pass that costs the most.
10. **Guard against context loss**: rebuild all resources on `webglcontextrestored`.
11. **Dispose** programs, buffers, textures, and framebuffers on teardown.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| API | WebGL2 (preferred), WebGL1 fallback, WebGPU (modern) |
| Shader authoring | GLSL ES 3.00, glslang validation, online tools for quick checks |
| Debugging | Spector.js, Chrome GPU inspector, WebGL Inspector |
| Math | gl-matrix |
| Profiling | `EXT_disjoint_timer_query_webgl2`, Chrome tracing, Safari GPU tools |
| Testing | Playwright screenshot comparison, headless GPU caveats noted |

## 7. Practical Implementation

**Context + capability detection:**

```ts
export function createGL(canvas: HTMLCanvasElement) {
  const gl = canvas.getContext("webgl2", {
    antialias: true, alpha: false, depth: true, stencil: false,
    powerPreference: "high-performance", preserveDrawingBuffer: false,
  });
  if (!gl) throw new Error("WebGL2 unavailable");

  const caps = {
    colorBufferFloat: !!gl.getExtension("EXT_color_buffer_float"),
    floatLinear: !!gl.getExtension("OES_texture_float_linear"),
    maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE) as number,
    maxVaryings: gl.getParameter(gl.MAX_VARYING_VECTORS) as number,
  };

  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); /* stop loop */ });
  canvas.addEventListener("webglcontextrestored", () => { /* rebuild resources */ });
  return {gl, caps};
}
```

**Shader compile with real error reporting:**

```ts
function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader) ?? "unknown error";
    gl.deleteShader(shader);
    throw new Error(`shader compile failed: ${log}`);
  }
  return shader;
}

function link(gl: WebGL2RenderingContext, vsSrc: string, fsSrc: string): WebGLProgram {
  const vs = compile(gl, gl.VERTEX_SHADER, vsSrc);
  const fs = compile(gl, gl.FRAGMENT_SHADER, fsSrc);
  const program = gl.createProgram()!;
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`link failed: ${gl.getProgramInfoLog(program)}`);
  }
  gl.deleteShader(vs); gl.deleteShader(fs);
  return program;
}
```

**Shader pair (vertex + fragment) with attributes:**

```glsl
#version 300 es
// vertex
layout(location = 0) in vec2 a_pos;
layout(location = 1) in vec2 a_uv;
out vec2 v_uv;
void main() {
  v_uv = a_uv;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
```

```glsl
#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 outColor;
uniform sampler2D u_tex;
uniform float u_time;
void main() {
  vec2 uv = v_uv;
  uv.x += sin(uv.y * 12.0 + u_time) * 0.004;   // subtle wave
  outColor = texture(u_tex, uv);
}
```

**Interleaved VAO setup:**

```ts
function makeQuadVAO(gl: WebGL2RenderingContext) {
  const verts = new Float32Array([
    -1, -1, 0, 1,
     1, -1, 1, 1,
    -1,  1, 0, 0,
     1,  1, 1, 0,
  ]);
  const vao = gl.createVertexArray()!;
  gl.bindVertexArray(vao);
  const vbo = gl.createBuffer()!;
  gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
  gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 16, 0);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 16, 8);
  gl.bindVertexArray(null);
  return {vao, vbo};
}
```

**Framebuffer ping-pong for multi-pass effects:**

```ts
function createTarget(gl: WebGL2RenderingContext, w: number, h: number) {
  const tex = gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

  const fbo = gl.createFramebuffer()!;
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  const status = gl.checkFramebufferStatus(gl.FRAMEBUFFER);
  if (status !== gl.FRAMEBUFFER_COMPLETE) throw new Error(`FBO incomplete: ${status}`);
  return {fbo, tex, w, h};
}
```

**Instanced draw (one call, many objects):**

```ts
gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, instanceCount);
// with per-instance attributes via vertexAttribDivisor(loc, 1)
```

**GPU timer (best-effort):**

```ts
const ext = gl.getExtension("EXT_disjoint_timer_query_webgl2");
if (ext) {
  const q = gl.createQuery()!;
  gl.beginQuery(ext.TIME_ELAPSED_EXT, q);
  drawScene();
  gl.endQuery(ext.TIME_ELAPSED_EXT);
  // poll later: gl.getQueryParameter(q, gl.QUERY_RESULT) in nanoseconds
}
```

**Graceful fallback:**

```ts
try {
  const {gl} = createGL(canvas);
  start(gl);
} catch (err) {
  console.warn("WebGL unavailable, showing static image", err);
  showFallbackImage();
}
```

## 8. Quality Standards

- WebGL2 with an explicit fallback path; no unhandled initialization failure.
- Every shader compile/link is checked with error logging surfaced to the console.
- Precision qualifiers chosen deliberately; mobile tested.
- Draw calls and state changes minimized; instancing for repeated geometry.
- No `readPixels`/`getError` in the render loop.
- Context loss and restoration handled by full resource rebuild.
- All GPU resources disposed on teardown.
- Frame budget met on target low-end hardware.

## 9. Verification and Testing

- Spector.js capture of one frame: verify draw calls, textures, programs, and no redundant binds.
- Frame-time measurement over 10 seconds on a mid-tier Android device.
- Shader compile test across Chrome, Firefox, Safari (WebKit differences matter).
- Context-loss simulation: call `WEBGL_lose_context.loseContext()` and verify recovery.
- Visual regression with a fixed time uniform (deterministic frames).
- Memory: repeated init/dispose cycles show no growth.

## 10. Security Considerations

- Never compile shaders from user input; GLSL is executable and a denial-of-service vector (infinite loops in fragment shaders can hang the GPU).
- Cap shader complexity and loop bounds; validate any dynamic shader assembly against an allowlist.
- WebGL exposes GPU/driver info via `getParameter`; do not rely on it for security decisions.
- Cross-origin textures need CORS and may leak pixel data if misconfigured.
- `preserveDrawingBuffer: true` keeps frame data readable by scripts—avoid unless required.
- Side-channel research (timing attacks via shaders) exists; do not run untrusted shader workloads in security-sensitive contexts.

## 11. Failure Handling

- **Shader compiles in Chrome, fails in Safari:** WebGL1 semantics in a WebGL2 shader, missing precision qualifier, or reserved words; test on each target.
- **Black screen:** check `gl.getError()` after init, framebuffer completeness, and whether the fragment shader writes to the bound output.
- **Banding/precision artifacts on mobile:** switch position math to `highp` and reduce the use of `mediump` in iterative calculations.
- **Frame rate halves on resize:** render target or canvas size doubled with pixel ratio—cap DPR at 2.
- **Context loss in the wild:** implement restoration; log it as an event rather than silently failing.
- **Timer queries unsupported:** they are disabled on many browsers for security; use wall-clock frame timing with `performance.now()` deltas as a proxy.

## 12. Expected Deliverables

1. Context initialization and capability detection code.
2. Shader sources with compile/link error handling.
3. Buffer/VAO layout documentation.
4. Render loop and pass structure (with framebuffers if used).
5. Fallback and context-loss handling.
6. Profiling results and budget compliance.
7. Disposal routine.

## 13. References

- MDN WebGL2 — https://developer.mozilla.org/en-US/docs/Web/API/WebGL2RenderingContext
- WebGL 2.0 specification — https://registry.khronos.org/webgl/specs/latest/2.0/
- GLSL ES 3.00 spec — https://registry.khronos.org/OpenGL/specs/es/3.0/GLSL_ES_Specification_3.00.pdf
- WebGL best practices (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices
- Spector.js — https://github.com/BabylonJS/Spector.js
- WebGPU specification — https://www.w3.org/TR/webgpu/
- Khronos WebGL wiki — https://www.khronos.org/webgl/wiki/Main_Page
