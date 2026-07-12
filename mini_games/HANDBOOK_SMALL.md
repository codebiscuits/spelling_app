# The Browser Mini-Game Handbook (compact edition)

Rules and recipes for the single-file HTML canvas toys in this folder.
Constraints: one HTML file, no build step, no libraries, no assets.
The full version with explanations and references is `HANDBOOK.md`.

## 0. House standards (mandatory for every game)

1. **Mouse-first, and mouse-only by default.** Games are played on a desktop
   with a mouse — never a touch screen. Every game must give a distinct,
   satisfying job to each of the four mouse inputs:
   - **movement** — steer, aim, stir, attract; the cursor must matter even
     with no button held,
   - **left button** — the primary verb: spawn, grab, draw, pour,
   - **right button** — a second verb, not a context menu: explode, erase,
     repel, tear,
   - **scroll wheel** — a continuous parameter: size, count, zoom, symmetry.
2. **Keyboard is optional seasoning.** Add keys only when they make the game
   more fun or interesting — when there are more parameters worth playing
   with than the mouse alone can carry (toggles, clear/reset, pause, mode
   cycling). Never put the core fun behind a keyboard control.
3. **The controls pane.** Every game shows a small frosted-glass panel fixed
   in the **top-left corner** listing every control and what it does, plus
   live state values where useful (counts, sizes, on/off states). House
   style: `position: fixed; top: 16px; left: 16px`, dark translucent
   background, `backdrop-filter: blur()`, rounded corners,
   `pointer-events: none` so it never eats input.
4. **No touch support.** Don't spend effort on touch events, multi-touch,
   gestures, or mobile affordances. Plain mouse events are fine. Any game
   using the right button must `preventDefault()` the `contextmenu` event.
5. **A reset button.** Every game has a visible button that instantly returns
   the simulation to its initial state — exactly as if freshly launched —
   without reloading the page. House style: a pill button fixed at the
   bottom-centre (`bottom: 24px; left: 50%; transform: translateX(-50%)`).
   A keyboard shortcut may supplement the button, never replace it.

## 1. Philosophy

Priority order: (1) **respond instantly** — the first mouse movement does
something visible within one frame, no menus; (2) **simulate, don't
animate** — the toy has real internal state and emergent behaviour;
(3) **reward experimentation** — every input combination does something.
Spend the complexity budget on one perfectly-tuned interaction, not five
mediocre features.

## 2. Engine bones (use in every game)

**Fixed timestep** — physics constants mean the same thing on every monitor:

```js
const DT = 1 / 60;
let acc = 0, last = performance.now();
function frame(now) {
  acc += Math.min((now - last) / 1000, 0.1); // clamp guards tab-switch spiral
  last = now;
  while (acc >= DT) { update(DT); acc -= DT; }
  draw();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
```

**Crisp DPR-aware canvas** — otherwise blurry on most screens:

```js
function fitCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2); // cap for perf
  w = window.innerWidth; h = window.innerHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // keep drawing in CSS pixels
}
```

**Mouse wiring** for the full house vocabulary:

```js
canvas.addEventListener('contextmenu', e => e.preventDefault());
canvas.addEventListener('mousedown', e => {
  if (e.button === 0) { /* left verb */ }
  if (e.button === 2) { /* right verb */ }
});
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  size = Math.max(3, Math.min(80, size - Math.sign(e.deltaY) * 2));
}, { passive: false });
```

- On `mousemove`, read `e.buttons` (bit 1 = left, bit 2 = right) instead of
  hand-rolled booleans, which go stale off-canvas.
- Listen for `mouseup` on `window`, not the canvas, so drags ending outside
  don't stick.
- Always normalise wheel deltas with `Math.sign(e.deltaY)`.

## 3. Physics recipes

**Verlet + constraints — the workhorse** (ropes, cloth, ragdolls, blobs;
unconditionally stable):

```js
// integrate: velocity is implicit in (pos - prevPos)
const vx = (p.x - p.px) * DAMPING, vy = (p.y - p.py) * DAMPING;
p.px = p.x; p.py = p.y;
p.x += vx; p.y += vy + GRAVITY;
// distance constraint: move both ends toward rest length
const dx = b.x - a.x, dy = b.y - a.y;
const dist = Math.hypot(dx, dy), diff = (dist - rest) / dist * 0.5;
a.x += dx * diff; a.y += dy * diff;
b.x -= dx * diff; b.y -= dy * diff;
```

Iterate constraints several times per step; more iterations = stiffer.
Soft-body jelly blob = ring of points + perimeter distance constraints +
pressure (compare shoelace area to rest area, push points outward along
normals by the deficit). Tearing = deactivate over-stretched constraints.
A "rigid" box = 4 verlet points + 6 constraints (edges + diagonals).

**Damped spring — the game-feel equation.** Use for cameras, UI, followers,
anything moving toward a target:

```js
vel += (target - pos) * omega * omega * dt;  // omega ≈ 8–20
vel *= Math.exp(-2 * omega * dt);
pos += vel * dt;
// no-overshoot one-liner (frame-rate independent):
pos += (target - pos) * (1 - Math.exp(-speed * dt));
```

**Spatial hash grid** — needed above ~300 colliding particles; enables
5,000–20,000 on Canvas 2D. Cell size = max diameter; insert each particle
per frame; test only the 9 neighbouring cells. Resolve overlaps by pushing
circles apart half the overlap each.

**Falling sand CA**: world in one `Uint8Array` of material ids; iterate
bottom-to-top, alternate scan direction per row; mark cells updated per
frame so grains fall one cell per step. Materials as data rules (sand sinks
through water; water flows sideways; fire ignites neighbours and rises;
plant grows into water; steam rises then condenses). Render by writing an
`ImageData` sized to the cell grid, then `drawImage` scaled up with
`imageSmoothingEnabled = false`.

**Fluids, two attainable paths**: (a) Stam "stable fluids" on a coarse grid
(64–256²): add forces from pointer, semi-Lagrangian advect, diffuse, project
divergence-free (~20 Jacobi iterations), advect a dye field — cannot blow
up. (b) Clavet 2005 particle fluid: verlet particles + spatial hash +
double-density relaxation, ~120 lines, 1–3k splashy particles; render with
the metaball goo trick (§4).

**Boids** (separation/alignment/cohesion) get much better with: a pointer
predator prey flee from; perception cones instead of radius; multiple
species with an asymmetric attract/fear matrix (= "Particle Life").

**Orbits**: use semi-implicit Euler (update velocity *then* position) so
orbits don't spiral; soften gravity `F = G·m₁·m₂ / (d² + ε²)`.

**Flow fields**: use curl noise (`vx = ∂n/∂y, vy = -∂n/∂x` by finite
differences) — divergence-free, so particles swirl forever instead of
clumping.

**Heightfield water** — ripples in a few lines; poke a height, waves
propagate and reflect:

```js
for (let i = 1; i < N - 1; i++)
  v[i] += ((u[i-1] + u[i+1]) * 0.5 - u[i]) * 0.3;
for (let i = 0; i < N; i++) { v[i] *= 0.99; u[i] += v[i]; }
```

## 4. Art rules

- **No raw HSL rainbows** — they read as programmer art. Use a cosine
  palette instead:

  ```js
  const pal = t => [0, 1, 2].map(i =>
    a[i] + b[i] * Math.cos(6.28318 * (c[i] * t + d[i])));
  // a=b=[.5,.5,.5], c=[1,1,1], d=[0,.33,.67] → balanced rainbow
  // d=[.30,.20,.20] → sunset;  c=[1,.7,.4], d=[0,.15,.20] → ocean
  ```

  Or `oklch(70% 0.15 hue)` (perceptually even), or 4–6 colours from a
  curated palette (lospec.com) and nothing else.
- **Never pure-black backgrounds** — use e.g. `#0c0c1e` or a subtle radial
  gradient.
- **Glow = additive blending + pre-rendered sprites.** Set
  `ctx.globalCompositeOperation = 'lighter'` and draw radial-gradient
  sprites pre-rendered *once* to a small offscreen canvas. Never use
  `ctx.shadowBlur` per particle — it's a full blur pass per shape.
- **Trails**: fading with a low-alpha background `fillRect` never fully
  fades (permanent ghosting). Instead fade with
  `globalCompositeOperation = 'destination-out'` and
  `rgba(0,0,0,0.08)`, then switch back to `'lighter'` to draw.
- **Gooey metaballs, fast**: draw plain circles to an offscreen canvas, then
  `ctx.filter = 'blur(12px) contrast(30)'` when compositing — blobs merge
  and split like mercury at full resolution.
- **Cheap post-processing**: draw scene sharp + again blurred with
  `'lighter'` = bloom; radial-gradient vignette with `'multiply'`.
- **Pixel-art mode**: render to a tiny canvas (e.g. 240×135), upscale with
  `image-rendering: pixelated` — instant coherent style and ~30× cheaper
  fills.
- **Value noise / FBM / domain warping** (`noise(p + k·noise(p))`) for
  organic texture: wind, clouds, wobbly lines, flames.
- **Jump to WebGL only** when the effect is inherently per-pixel (full-res
  fluid dye, 100k particles, reaction-diffusion). Prototype in Canvas 2D
  first.
- **Lens/optics effects** are all one trick: sample the scene at a warped
  coordinate, `scene(warp(p))` — kaleidoscope (fold angle into a mirrored
  sector, sample radius scaled ×1.2–1.5 past the rim), magnifier, swirl,
  ripple. Fade the warp near the rim with smoothstep; run it three times
  with ±3–6% strength per RGB channel for rainbow dispersion.

## 5. Juice (highest ROI — do all of these)

- **Ease everything**; nothing moves linearly. `easeOutBack` /
  `easeOutElastic`, or drive with §3's spring.
- **Squash and stretch**: `scaleY = 1 + vy * 0.02; scaleX = 1 / scaleY`.
- **Particles on every event** (spawn, pop, collision): 5–30 short-lived,
  `'lighter'` blended, from a pre-allocated pool.
- **Screen shake done right**: keep `trauma` in [0,1], add on events, decay
  each frame, shake offset *and rotation* by `trauma²` using smooth noise.
  Small doses.
- **Hit-stop**: freeze the sim 40–80 ms on big impacts.
- **Sound from nothing**: Web Audio oscillator → gain envelope, or ZzFX
  inline. Pitch by object size; snap pitches to a pentatonic scale
  (`220 * 2 ** ([0,2,4,7,9][i % 5] / 12)`) so random events sound musical.
- **Ambient life**: nothing perfectly still — idle wobble, blinking,
  drifting parallax.

## 6. Performance

- Frame budget 16.6 ms. Measure first (DevTools Performance): script-bound
  vs paint-bound need different fixes.
- **Zero allocation in the hot loop**: particle pools (revive/kill, never
  push/splice), no per-particle strings — precompute ~64 fillStyles into an
  array and index.
- **Typed arrays** (structure-of-arrays: `Float32Array` per component) for
  sims over ~5,000 particles.
- **Batch by state**: group by colour, many shapes per `beginPath`.
- **Layer canvases**: static background drawn once on its own canvas.
- **Reuse `ImageData`** buffers; max one get/put round trip per frame, on
  the smallest buffer possible.
- Canvas 2D budget intuition: ~10k `drawImage` sprites, ~50k `fillRect`s,
  ~1 full-screen filter, ~2M typed-array cell updates per frame.
- Pause on `visibilitychange`.

## 7. Designing for children (this app's audience)

- **No fail states, no game over** — these are toys, not tests.
- **Every input does something**; random mashing always produces a result.
- **The toy teaches itself** through the first poke — the controls pane is
  for grown-ups.
- Respect `prefers-reduced-motion`; avoid full-screen flashing.
- **Sound off by default** (classrooms), with a friendly mute toggle.
- **Max chaos is the designed state**: children will instantly spawn the
  maximum of everything, so tune for that.

## 8. Proven toy recipes

Jelly blobs (pressure soft body + googly eyes + pentatonic pops) · pond
(heightfield water + buoyant verlet ducks) · goo lamp (blur+contrast
metaballs + convection) · ink garden (stable fluids + dye) · falling sand
with materials · verlet puppet creatures · firefly boids with synchronised
blinking · SPH splash water with goo render · raycast shadow maze ·
particle-life zoo · kaleidoscope mandala painter · verlet-box wrecking yard ·
topple tower (stacked verlet boxes collapse under gravity; scroll tunes
gravity/bounciness, click a block to explode or morph it, right-click gives
it its own gravitational pull).

*Build the engine bones (§2), pick one toy, then spend the last 20% of the
time entirely on juice (§5).*
