# The Browser Mini-Game Handbook

**Pushing the limits of self-contained JS canvas toys: physics, art, and feel.**

This is a guide for building the kind of browser mini-game that makes people say
"wait, this is just a web page?" Everything here works in a single HTML file with
no build step, no libraries, and no assets — the same constraints as the games in
this folder. Each section pairs the *inspiration* (what's possible, who's done it
brilliantly) with the *technique* (how to actually get there).

> **Reference implementations:** [`jelly.html`](jelly.html) ("Jelly Buddies")
> was built from this handbook and is annotated with section references
> throughout. It demonstrates the engine bones (§2.1–2.3), pressure soft bodies
> (§3.1), spring-driven pop-in (§3.2), cosine palettes (§4.1), glow sprites and
> additive particles (§4.2), and the juice checklist — trauma² screenshake,
> pentatonic synth sounds off by default, blinking eyes, ambient bokeh (§5, §7).
> [`lens_lab.html`](lens_lab.html) ("Lens Lab") is the shader-side companion:
> a full-screen fragment shader (§4.9) with draggable composable lenses,
> kaleidoscope folds, and chromatic dispersion (§4.10).

---

## Table of contents

1. [Philosophy: what makes a toy feel incredible](#1-philosophy)
2. [Engine bones: the loop, the canvas, the input](#2-engine-bones)
3. [Physics cookbook](#3-physics-cookbook)
4. [Art style cookbook](#4-art-style-cookbook)
5. [Juice: the difference between "works" and "wow"](#5-juice)
6. [Performance playbook](#6-performance-playbook)
7. [Designing for small hands](#7-designing-for-small-hands)
8. [Idea gallery: toys worth building](#8-idea-gallery)
9. [Reading list](#9-reading-list)

---

## 1. Philosophy

A great browser toy has three properties, in priority order:

1. **It responds instantly.** The first pointer movement must do something
   visible within one frame. No menus, no instructions needed. The cloth sim in
   this folder gets this right: you move the mouse and the cloth ripples.
2. **It's a simulation, not an animation.** The magic feeling comes from
   emergence — the user pokes a *system* and the system answers in ways even the
   author didn't script. This is why cloth, sand, boids, and fluids are
   perennial: they have genuine internal state and dynamics.
3. **It rewards experimentation.** Every input combination should do something.
   Tearing cloth, drawing walls in sand, flinging a soft body — the toy should
   be *deeper* than it looks, not shallower.

The corollary: **spend your complexity budget on the simulation and the feel,
not on features.** One perfectly-tuned interaction beats five mediocre ones.

---

## 2. Engine bones

Three pieces of infrastructure separate a demo that feels professional from one
that feels like a school project. Get these right once, reuse everywhere.

### 2.1 Fixed timestep with interpolation

Most of the games in this folder step physics once per `requestAnimationFrame`.
That means the simulation runs at whatever the display refresh is — 60 Hz on one
laptop, 144 Hz on a gaming monitor, 30 Hz when the tab is struggling. Verlet
cloth simulated at 144 Hz is *stiffer and faster* than at 60 Hz; sand falls at
half speed on a slow machine. The fix is the classic **fixed timestep**
(Glenn Fiedler, "Fix Your Timestep!"):

```js
const DT = 1 / 60;           // simulation runs at exactly 60 steps/sec
let acc = 0, last = performance.now();

function frame(now) {
  acc += Math.min((now - last) / 1000, 0.1);  // clamp: tab-switch spiral guard
  last = now;
  while (acc >= DT) { update(DT); acc -= DT; }
  draw(acc / DT);            // pass leftover fraction for interpolation
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
```

For rendering, interpolate between the previous and current physics positions
using that leftover fraction (`x = prev + (curr - prev) * alpha`). For casual
toys you can skip interpolation, but keep the fixed step — it makes every
constant in your simulation (gravity, spring stiffness, damping) mean the same
thing on every machine, which makes tuning *possible*.

### 2.2 A crisp, DPR-aware canvas

`canvas.width = window.innerWidth` renders at CSS-pixel resolution — blurry on
every phone and most laptops (devicePixelRatio 2–3). The upgrade:

```js
function fitCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2); // cap for perf
  w = window.innerWidth; h = window.innerHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);   // draw in CSS pixels as before
}
```

All your existing coordinate code keeps working (you still think in CSS pixels)
but lines and text are suddenly razor sharp. The `Math.min(dpr, 2)` cap matters:
a 3× phone screen is 9× the pixels, and per-pixel effects will drown.

Exception: deliberately low-res styles (pixel art, metaballs) *want* a small
buffer — see §4.6.

### 2.3 Pointer events, not mouse events

`mousemove`/`mousedown` ignore touch. One substitution makes every toy work on
tablets — which is where children actually play:

```js
canvas.addEventListener('pointerdown', e => { canvas.setPointerCapture(e.pointerId); /* ... */ });
canvas.addEventListener('pointermove', e => { /* e.clientX/Y as before */ });
canvas.addEventListener('pointerup',   e => { /* ... */ });
// and in CSS:  canvas { touch-action: none; }   — stops scroll/zoom stealing the gesture
```

`e.pointerId` gives you multi-touch for free: keep a `Map` of active pointers
and suddenly two children can poke the same cloth simultaneously. Multi-touch on
a physics toy is a *huge* upgrade for very little code.

---

## 3. Physics cookbook

The techniques below are ordered roughly by effort. Each entry says what it
gives you, the core maths, and the trick that makes it stable.

### 3.1 Verlet integration + constraints — the workhorse

Already used by `cloth.html`, and it's the right choice: position-based Verlet
is unconditionally stable in a way force-based springs are not. The pattern
generalises far beyond cloth:

```js
// integrate: velocity is implicit in (pos - prevPos)
const vx = (p.x - p.px) * DAMPING;
const vy = (p.y - p.py) * DAMPING;
p.px = p.x; p.py = p.y;
p.x += vx; p.y += vy + GRAVITY;

// constraint: move both ends toward rest distance
const dx = b.x - a.x, dy = b.y - a.y;
const dist = Math.hypot(dx, dy);
const diff = (dist - rest) / dist * 0.5;
a.x += dx * diff; a.y += dy * diff;
b.x -= dx * diff; b.y -= dy * diff;
```

Iterate all constraints several times per step (Gauss-Seidel relaxation). More
iterations = stiffer material. From these two primitives you can build:

- **Rope / chain / hair** — a line of points with distance constraints. Add a
  bending constraint (distance constraint between point *i* and *i+2* at 2×
  rest) for stiff hair vs. floppy rope.
- **Ragdolls and creatures** — sticks between joints; pin one point to the
  pointer and you have a puppet.
- **Soft-body blobs (the star of the show)** — a ring of points with (a)
  distance constraints around the perimeter and (b) a **pressure constraint**:
  compute the polygon's current area with the shoelace formula, compare to rest
  area, and push each point outward along its normal proportional to the
  deficit. The result is a squishy jelly ball that squashes on landing and
  wobbles — one of the most delightful objects you can put under a child's
  finger. See "soft body pressure model" (Matyka).
- **Tearing** — already in `cloth.html`: deactivate a constraint when stretched
  past a threshold. Works for ropes and blobs too.

**Modern umbrella term:** Position-Based Dynamics (Müller et al.), and its
successor **XPBD**, which adds a compliance term so stiffness is
iteration-count-independent. For a mini-game plain Verlet is fine; read the
XPBD paper when you want rigid bodies and cloth interacting in one solver.

### 3.2 The damped spring — the single most useful equation in game feel

Not for physics objects — for *everything else*. Camera, UI, cursor followers,
score counters, anything that should move smoothly toward a target:

```js
// critically-ish damped spring; omega = responsiveness (try 8–20)
vel += (target - pos) * omega * omega * dt;
vel *= Math.exp(-2 * omega * dt);   // damping
pos += vel * dt;
```

Anything driven by this feels *alive* instead of mechanical. A follower chain of
10 circles each springing toward the previous one is a complete toy by itself
(this is how every "wormy cursor pet" works). The cheap one-liner version, for
when you don't need overshoot:
`pos += (target - pos) * (1 - Math.exp(-speed * dt))` — an exponential ease
that's frame-rate independent, unlike the common `pos += (target-pos)*0.1`.

### 3.3 Thousands of particles: spatial hashing

The ball pit and any particle-collision toy hits a wall at O(n²) pair checks —
roughly 300–500 interacting circles. A **uniform spatial hash grid** takes you
to 5,000–20,000 on Canvas 2D and 100,000+ on WebGL:

```js
const CELL = maxRadius * 2;
const grid = new Map();
const key = (x, y) => ((x / CELL) | 0) * 73856093 ^ ((y / CELL) | 0) * 19349663;

// each frame: clear, insert every particle by key, then for each particle
// only test the 9 cells around it.
```

Combine with Verlet-style position correction for the collision response
(push overlapping circles apart by half the overlap each) and you get an
extremely stable ball pit with no tunnelling and no explosion, even under a
dragging pointer. This one data structure unlocks: ball pits at 10× the count,
particle fluids (§3.5), crowd/boid sims at scale, and granular material.

For serious counts, store particles in **typed arrays** (`Float32Array` for
x, y, px, py) instead of objects — see §6.

### 3.4 Falling sand, properly — cellular automata with materials

`sand.html` is the seed of a genre (Powder Toy, Noita). The classic sand rule —
fall down, else down-left/down-right — is three lines. The depth comes from
**materials as data**:

| Material | Rule sketch |
|---|---|
| Sand | falls; sinks through water |
| Water | falls, then flows sideways (random walk along the surface) |
| Oil | like water, lower density, floats on it |
| Fire | short lifetime; ignites neighbours that are flammable; rises |
| Plant | static; grows into adjacent water; flammable |
| Steam | inverse gravity; condenses back to water after a while |
| Wall | static, indestructible |

Implementation notes that matter:

- Store the world as a single `Uint8Array` (material id per cell), not objects.
- Iterate **bottom-to-top** for falling materials, and alternate left-to-right /
  right-to-left scan direction per row (or per frame) to avoid directional bias.
- Give each cell an "updated this frame" bit (or use a frame-parity trick) so a
  grain doesn't fall multiple cells per step.
- **Chunking:** divide the world into 32×32 chunks with a dirty flag; skip
  simulation and redraw for chunks where nothing moved. This is the difference
  between a 200×150 world and a full-screen 1920×1080-cell world.
- Render by writing directly into an `ImageData` buffer sized to the *cell*
  grid, then `drawImage` the small canvas scaled up with
  `imageSmoothingEnabled = false` — chunky pixels are the correct aesthetic
  here, and it's ~100× cheaper than drawing rects.

Two or three interacting materials produce endless emergent play: water + sand
+ plant is already a gardening toy; add fire and it's a story generator.

### 3.5 Real fluids — two attainable paths

Fluid simulation sounds like a research project; two versions are genuinely
achievable in an evening each:

**a) Grid-based "stable fluids" (Jos Stam, 1999) — ink, smoke, dye.**
A velocity field on a coarse grid (64×64–256×256), with four steps per frame:
add forces (from pointer drag), advect the velocity field through itself
(semi-Lagrangian: trace backwards, sample bilinearly), diffuse, and
project (make the field divergence-free with ~20 Jacobi iterations). Then
advect a colour/dye field through the velocity field and render it. It is
unconditionally stable — you cannot blow it up — and dragging your finger
through swirling ink is mesmerising. This is exactly what the famous
"WebGL Fluid Simulation" (Pavel Dobryakov) demo does on GPU; a 128×128 CPU
version in JS runs fine and looks gorgeous rendered soft. Mike Ash's
"Fluid Simulation for Dummies" is the friendliest walkthrough.

**b) Particle fluids (SPH-lite) — water you can splash.**
Full SPH is fiddly, but the **Clavet et al. 2005 "Particle-based Viscoelastic
Fluid Simulation"** algorithm is famously simple and stable: it's Verlet
particles + spatial hash + a "double density relaxation" step that pushes
particles apart based on local density (with separate near-density to prevent
clumping). ~120 lines total. 1,000–3,000 particles of splashy, pourable water
on Canvas 2D. Render it with the metaball goo trick (§4.3) and you have a
liquid toy children will not put down. This is also the algorithm behind the
liquids in *PixelJunk Shooter* and many "sandbox water" games.

### 3.6 Boids and steering — life from three rules

`boids.html` covers the classics (separation, alignment, cohesion — Craig
Reynolds 1987). Ways to push it much further:

- **Predator/prey**: one pointer-controlled predator that flocks flee; prey
  "eaten" respawn as new flockmates. Instant game.
- **Perception cones** instead of radius (dot product with heading) — flocks
  become visibly directional and lifelike.
- **Species** with different parameters and inter-species rules (fear/attract
  matrix). Two lines of code, endless variety — this is the whole mechanic of
  the popular "Particle Life" simulations (asymmetric attraction matrices
  between coloured particle species produce cell-like crawling creatures;
  search *Particle Life / Clusters, Jeffrey Ventrella*).
- **Trail rendering** (§4.2) turns flocks into calligraphy.

### 3.7 Orbits and n-body

`gravity_well.html` / `orbits.html` territory. Upgrades worth knowing:

- Use **semi-implicit (symplectic) Euler** — update velocity *then* position.
  Same cost as regular Euler but orbits stop spiralling outward/inward. This
  single-line change is the difference between orbits that decay and orbits
  that persist for minutes.
- Soften gravity near zero distance: `F = G·m₁·m₂ / (d² + ε²)` kills the
  slingshot-to-infinity glitch.
- For thousands of mutually-gravitating bodies, the **Barnes-Hut quadtree**
  (O(n log n)) is the classic; in practice a coarse grid of summed
  mass-centroids gets you 90% of the way with far less code.

### 3.8 Rigid bodies without a library

For boxes/polygons that stack and topple you generally want impulse-based
resolution (see Chris Hecker's classic articles or Randy Gaul's "How to Create
a Custom Physics Engine" series). Honest advice: **for a mini-game, fake it.**
Circles + verlet points cover 95% of toy ideas, and a "rigid" box can be four
verlet points with six distance constraints (edges + diagonals) — it tumbles,
stacks, and squashes charmingly, and it's ten lines on top of §3.1. This is
the secret of many "physics" browser games.

### 3.9 Flow fields and curl noise

`flow.html` / `magnetic_lines.html` territory. The pro move is **curl noise**:
instead of using noise directly as an angle, take the curl of a noise field
(`vx = ∂n/∂y`, `vy = -∂n/∂x`, computed by finite differences). Curl fields are
divergence-free, so particles *swirl forever* instead of clumping into sinks.
This is the technique behind virtually every beautiful "particles flowing like
silk" demo. Animate the noise's third dimension slowly for a field that evolves
over time. (Inline simplex noise implementation: §4.5.)

### 3.10 Heightfield water — ripples in 30 lines

A criminally underused effect: a 1D or 2D array of surface heights where each
cell accelerates toward the average of its neighbours:

```js
// 1D version: u = heights, v = velocities
for (let i = 1; i < N - 1; i++)
  v[i] += ((u[i-1] + u[i+1]) * 0.5 - u[i]) * K;   // K ≈ 0.3
for (let i = 0; i < N; i++) { v[i] *= 0.99; u[i] += v[i]; }
```

Touch it (set a height) and perfect ripples propagate, reflect off edges, and
interfere. Draw it as a filled polygon with a gradient and you have a pond;
float verlet objects on it (buoyancy = push up proportional to submerged depth)
and you have a bath toy. The 2D version on a coarse grid gives you rain-on-a-
puddle. This pairs beautifully with the liquid pour game already in this folder.

---

## 4. Art style cookbook

Technique determines what's *possible*; style determines whether anyone cares.
The biggest wins here cost almost nothing.

### 4.1 Colour: stop using raw HSL rainbows

`hsl(hue, 72%, 50%)` sweeps are the "programmer art" tell — HSL's perceptual
lightness is wildly uneven (yellow glows, blue goes muddy). Three upgrades:

**a) Cosine gradient palettes (Iñigo Quilez).** One formula, infinite tasteful
palettes:

```js
// t in [0,1] → [r,g,b]; a,b,c,d are vec3 params
const pal = t => [0, 1, 2].map(i =>
  a[i] + b[i] * Math.cos(6.28318 * (c[i] * t + d[i])));
// e.g. a=[.5,.5,.5] b=[.5,.5,.5] c=[1,1,1] d=[.00,.33,.67]  → balanced rainbow
//      d=[.30,.20,.20]                                       → sunset
//      a=[.5,.5,.5] b=[.5,.5,.5] c=[1,.7,.4] d=[0,.15,.20]   → ocean/teal
```

Sample it for particle colours, field intensities, trail ages. It always looks
designed, never garish. IQ's article ("palettes") has a gallery of parameter
sets.

**b) OKLCH for programmatic colour.** Modern browsers accept
`oklch(70% 0.15 200)` in canvas fillStyle. Equal lightness *actually looks*
equal across hues, so varying only hue gives a professional palette
automatically.

**c) Limited palettes.** Pick 4–6 colours from a curated palette site
(lospec.com/palette-list is the pixel-art community's treasury) and use *only*
those. Constraint reads as art direction. A falling-sand game in a 6-colour
palette looks like a finished indie game; the same sim in random RGB looks like
a tech demo.

Also: **never use pure black backgrounds.** `#0c0c1e` (as the cloth game
already does) or a subtle radial gradient from `#1a1230` to `#0a0818` adds
depth for free.

### 4.2 Glow, trails, and additive light

The signature look of great canvas demos is *light*, not paint:

```js
ctx.globalCompositeOperation = 'lighter';   // additive blending
```

Overlapping translucent particles now sum toward white like real light. Combine
with radial-gradient sprites instead of flat circles:

```js
// Pre-render ONCE to an offscreen canvas — shadowBlur per-particle is a perf trap
const spr = document.createElement('canvas'); spr.width = spr.height = 64;
const g = spr.getContext('2d').createRadialGradient(32, 32, 0, 32, 32, 32);
g.addColorStop(0, 'rgba(255,220,160,1)');
g.addColorStop(0.4, 'rgba(255,120,40,0.35)');
g.addColorStop(1, 'rgba(255,120,40,0)');
spr.getContext('2d').fillStyle = g; spr.getContext('2d').fillRect(0, 0, 64, 64);
// per particle: ctx.drawImage(spr, x-32, y-32)  — cheap, gorgeous
```

`ctx.shadowBlur` gives similar glow but costs a full blur pass *per shape* —
fine for 10 objects, fatal for 1,000. Pre-rendered gradient sprites are the
standard workaround.

**Trails: the fade-to-black bug.** The common trick (used in several games
here) — `fillRect` the whole canvas with low-alpha background each frame —
never fully fades: 8-bit alpha compositing stalls, leaving permanent ghost
smears. The fix is to fade with `destination-out` instead:

```js
ctx.globalCompositeOperation = 'destination-out';
ctx.fillStyle = 'rgba(0,0,0,0.08)';          // alpha = fade speed
ctx.fillRect(0, 0, w, h);
ctx.globalCompositeOperation = 'lighter';    // back to drawing
```

This erases *toward transparency*, which always completes, and lets you put a
CSS gradient behind the canvas as the visible background.

### 4.3 Gooey metaballs, the fast way

`metaballs.html` evaluates the field per pixel in JS — that's why it's limited
to `scale = 4` blockiness. The classic **blur + threshold** trick gets smooth,
full-resolution goo at a fraction of the cost:

```js
// draw blobs as plain blurry circles into an offscreen canvas, then:
ctx.filter = 'blur(12px) contrast(30)';      // contrast crushes the blur into
ctx.drawImage(offscreen, 0, 0);              // a hard, wobbly-merged edge
ctx.filter = 'none';
```

Blur makes nearby circles' soft edges overlap; extreme contrast thresholds the
result so the union has one smooth liquid boundary. Blobs visibly *merge and
split* like mercury. (For coloured goo: threshold the alpha channel via
`contrast` on a white-on-transparent buffer, then use it as a mask with
`source-in`.) This is the standard technique behind every "gooey" UI/lava-lamp
codepen, and it's exactly what the SPH water in §3.5b wants for rendering.

### 4.4 Screen-space filters and post-processing on Canvas 2D

`ctx.filter` accepts CSS filter chains and is your poor-man's post stack:
`blur()` for depth-of-field or dreaminess, `saturate()`/`hue-rotate()` for
mood shifts on events, `contrast()` for the goo trick. Draw your scene to an
offscreen canvas and composite it multiple times: once sharp, once blurred with
`lighter` on top = **instant bloom**. A subtle vignette (radial gradient,
`multiply`) plus faint noise grain (pre-rendered, `overlay`, 3% alpha) makes
any scene read as "graded" rather than raw.

### 4.5 Procedural texture: noise, FBM, domain warping

Ship a tiny simplex/value-noise function (20 lines, or the classic 2D hash
version below) and a world of organic texture opens up:

```js
// value noise: hash lattice points, smooth-interpolate between them
const hash = (x, y) => {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return s - Math.floor(s);
};
function noise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  return hash(xi, yi) * (1-u) * (1-v) + hash(xi+1, yi) * u * (1-v)
       + hash(xi, yi+1) * (1-u) * v + hash(xi+1, yi+1) * u * v;
}
// FBM: sum octaves →  n(p) + n(2p)/2 + n(4p)/4 ...  = clouds, terrain, marble
// Domain warping: noise(p + k·noise(p))  = the swirly organic look (IQ again)
```

Uses: wind fields for cloth, cloud backgrounds, wobbly hand-drawn line offsets,
terrain for a digging game, marble/wood textures, flame shapes. **Domain
warping** in particular is the one-weird-trick behind most "how is this so
organic" generative art.

### 4.6 Pixel-art mode and deliberate low-res

Render to a small canvas (e.g. 240×135) and upscale:

```css
canvas { image-rendering: pixelated; width: 100vw; height: 100vh; }
```

Every circle and line you draw becomes charming chunky pixels automatically —
an instant, coherent art style that also *cuts your fill cost 30×*. Falling
sand, particle games, and retro toys all benefit. The inverse move — render at
half resolution and upscale *smoothly* (default smoothing) — is the standard
trick for expensive full-screen effects like fluid dye fields, where softness
looks intentional.

### 4.7 The hand-drawn / wobble style

Nothing says "crafted" like lines that look drawn. The technique (as used by
rough.js, but easy to hand-roll): draw each line/circle as 2 overlapping passes
of a slightly-randomised path, offsetting each vertex by ±1.5px of noise, and
re-randomise the offsets only ~2× per second (not every frame — that reads as
noise, not sketchiness). Pair with an off-white paper background,
`multiply`-composited strokes, and a wobbling 2 Hz redraw and you get the
*Crayon Physics / GMTK-jam* look that is instantly warm and child-friendly.

### 4.8 2D lighting and shadows

Two levels:

- **Cheap and lovely:** darkness overlay (translucent dark fillRect on an
  offscreen "light canvas"), then punch holes in it with radial gradients using
  `destination-out` at each light source, then draw that canvas over the scene.
  Flickering torch = animate the gradient radius with noise.
- **Real 2D shadows:** raycast from the light to every polygon vertex (± tiny
  angular offsets), sort hits by angle, fill the resulting visibility polygon.
  Nicky Case's "Sight & Light" interactive essay is the definitive tutorial and
  the result — hard-edged sweeping shadows — is spectacular in a maze or
  hide-and-seek toy.

### 4.9 When to jump to WebGL / shaders

Canvas 2D tops out around: ~10–20k sprites, ~1 full-screen `ImageData` pass, a
couple of full-screen filters. If the vision is *per-pixel* — real-time fluid
dye at full res, raymarched blobs, CRT/warp effects, 100k particles — write one
fragment shader. The minimal harness is ~40 lines (compile shader, one
full-screen triangle, uniforms for time/pointer/resolution) with no libraries;
from there you're writing Shadertoy-style GLSL:

- **SDF scenes**: model shapes as signed-distance functions, get perfect
  anti-aliasing, glow, soft shadows, and morphing for free. IQ's 2D SDF page
  lists formulas for every shape.
- **Feedback buffers** (ping-pong two textures): reaction-diffusion
  (Gray-Scott — coral/fingerprint patterns from two chemicals), GPU fluids,
  infinite mirror trails, ecosystem CAs.
- **Instanced particles**: hundreds of thousands of points with physics in the
  vertex shader.

Rule of thumb: prototype in Canvas 2D; port to a shader only the *one* effect
that's pixel-bound. Many polished toys are Canvas 2D for logic with a single
WebGL post pass. (WebGPU + compute shaders is the 2026 frontier — million-
particle SPH in a browser — but WebGL2 remains the safe target.)

### 4.10 Lenses and fake optics

*(Reference implementation: [`lens_lab.html`](lens_lab.html) — draggable
kaleidoscope/crystal/prism/ripple lenses over a procedural light field.)*

Every 2D "optical" effect — refraction, magnification, kaleidoscopes, heat
shimmer, water distortion — is the same trick: **warp the coordinate you
sample the scene at.** Instead of computing `scene(p)`, compute
`scene(warp(p))`. That one idea, plus a handful of warp functions, is an
entire genre of toy. In a fragment shader it's per-pixel and free; on Canvas
2D a small magnifier can be faked with a clipped, scaled `drawImage` of the
region under it, but anything full-screen wants the shader.

The warp vocabulary (all operate on `d = p - centre`, `r = |d| / radius`,
applied only where `r < 1`):

- **Kaleidoscope fold** — convert to polar, wrap the angle into one sector,
  mirror it, convert back:
  `a = mod(atan(d.y, d.x), seg); a = min(a, seg - a);` with
  `seg = 2π / N`. Everything inside becomes an N-fold mandala. **The lesson
  learned the hard way:** also *scale the sample radius up* (`rad = |d| ×
  1.2–1.5`) so the fold reaches past the lens rim and pulls the surrounding
  scenery into the mandala — folding only the lens's own patch mirrors mush.
  Crisp source features (bright dots, stars, thin lines) fold into crisp
  spokes; soft gradients fold into soup, so give the background sharp detail.
- **Sphere/magnifier** — scale `d` by a factor that goes from `k < 1` at the
  centre (zoom in) to `1` at the rim: `p' = centre + d * mix(k, 1.0,
  pow(r, n))`. `k ≈ 0.4, n ≈ 1.7` reads as a crystal ball.
- **Swirl** — rotate `d` by an angle proportional to `(1 - r)`; the twist dies
  off at the rim so the boundary stays seamless.
- **Ripple** — displace radially by `sin(r·freq − t)·(1 − r)`; animated
  concentric water rings.

Three finishing moves turn "a warp" into "glass":

1. **Chromatic dispersion — the single biggest upgrade.** Run the warp three
   times with a slightly different strength per colour channel (±3–6%), then
   assemble `vec3(scene(pR).r, scene(pG).g, scene(pB).b)`. Every edge and fold
   seam fringes into rainbow — instantly expensive-looking, and physically the
   same reason real prisms make rainbows. Costs 3× the scene evaluation; on a
   GPU, irrelevant.
2. **Fade the warp at the rim.** Blend between warped and unwarped coordinates
   with `smoothstep(1.0, ~0.75, r)` so there's never a hard discontinuity at
   the lens edge.
3. **Sell the physical object**: a bright ring at `r ≈ 0.97`
   (`smoothstep` on `|r − 0.97|`), a fixed specular glint
   (`pow(max(cos(angle − θ_light), 0), 24)` on the ring), fresnel edge
   darkening inside the rim, and a saturation/brightness boost on the lens
   interior so looking through it is *better* than not.

Lenses **compose**: apply them sequentially to the coordinate before sampling
(`p = lensB(lensA(p))`) and overlapping a swirl with a kaleidoscope
kaleidoscopes the swirl. Let the user drag them and stack them — the
combinatorics are the toy.

---

## 5. Juice

"Juice" is the game-design term (from the Vlambeer talk "The Art of
Screenshake" and "Juice it or lose it", both on YouTube — required viewing) for
disproportionate audiovisual feedback. It's the highest ROI work in this entire
handbook. A checklist for every interaction in your toy:

- **Easing everywhere.** Nothing moves linearly. UI, spawns, deaths — pick from
  easings.net; `easeOutBack` (overshoot) and `easeOutElastic` are the toy-box
  stars. Or just drive everything with §3.2's springs.
- **Squash and stretch.** Scale anything by its velocity:
  `scaleY = 1 + vy * 0.02; scaleX = 1 / scaleY` (volume-preserving). A ball
  that flattens on bounce reads as *rubber*; one that doesn't reads as a
  *cursor*. Disney's first principle of animation, one line of code.
- **Particles on every event.** Spawn, collision, pop, milestone: 5–30 short-
  lived particles with `lighter` blending. Keep a pool (§6).
- **Screen shake, done right.** Don't offset randomly per frame. Keep a
  `trauma` value in [0,1], add to it on events, decay it, and shake by
  `trauma²` (or ³) using smooth noise for offset *and rotation* (Squirrel
  Eiserloh's GDC talk "Math for Game Programmers: Juicing Your Cameras").
  Rotation shake is the secret ingredient. Small doses: this is seasoning.
- **Hit-stop.** Freeze the simulation for 40–80 ms on big impacts. Sounds
  wrong, feels amazing — it's in every fighting game.
- **Sound from nothing.** Web Audio can synthesise every sound a toy needs —
  no files. **ZzFX** (~1 KB, public domain, designed to be pasted inline) gives
  you designed pops/boings/chimes from a parameter array. Or hand-roll:
  oscillator → gain envelope → destination; pitch pops by object size; a
  pentatonic scale (`freq = 220 * 2 ** (scale[i % 5] / 12)`, scale =
  [0,2,4,7,9]) makes *any* random event sequence sound musical instead of
  noisy — the classic toy-app trick. Add `navigator.vibrate(10)` on mobile
  taps.
- **Ambient life.** Nothing should be perfectly still, ever. Idle wobble from
  low-amplitude noise, blinking, drifting background parallax. Stillness reads
  as frozen; micro-motion reads as alive.

---

## 6. Performance playbook

The frame budget is 16.6 ms (or 8.3 on 120 Hz screens). How to spend it:

1. **Measure first.** DevTools → Performance tab; look at whether you're
   script-bound (physics) or paint-bound (drawing). The fixes are disjoint.
2. **Zero allocation in the hot loop.** GC pauses are the #1 cause of visible
   hitching. Pre-allocate particle **pools** (fixed-size array + freelist,
   revive/kill instead of push/splice), reuse scratch vectors, never create
   closures/arrays/strings per particle per frame. Building
   `\`hsl(${h},72%,50%)\`` for 5,000 particles allocates 5,000 strings per
   frame — precompute a palette array of 64 fillStyles and index into it.
3. **Typed arrays for big sims.** Structure-of-arrays
   (`x = new Float32Array(N)`, `y`, `px`, `py`…) is dramatically faster than
   arrays of objects at n > ~5,000: no pointer chasing, no GC, SIMD-friendly.
4. **Batch by state.** Every `fillStyle` change and every `beginPath` has cost.
   Group particles by colour bucket; draw many circles into one path per
   bucket where possible.
5. **Layer your canvases.** Static background on one canvas (drawn once), sim
   on a second, UI on DOM. Stacked canvases are free; redrawing a gradient sky
   every frame is not.
6. **`ImageData` discipline.** One `getImageData`/`putImageData` round trip
   per frame max, on the smallest buffer possible (see §4.6); `createImageData`
   every frame (as `metaballs.html` does) is an allocation of `w*h*4` bytes —
   allocate once, reuse.
7. **Workers + OffscreenCanvas.** Physics in a worker keeps input handling
   smooth even when the sim spikes; `OffscreenCanvas` lets the worker render
   too. Worth it only for the heaviest sims (fluids, 50k+ particles).
8. **Respect the tab lifecycle.** Pause on `visibilitychange` (the timestep
   clamp in §2.1 already prevents the tab-return explosion).

Budget intuition for Canvas 2D on a mid laptop: ~10k `drawImage` sprites,
~50k flat `fillRect`s, ~1 full-screen filter pass, ~2M cell-updates of typed-
array CA per frame. Plan the sim size around these, then push with the tricks
above.

---

## 7. Designing for small hands

These toys live inside a spelling app for primary-school children — that
audience sharpens some choices:

- **No fail states, no game over.** These are toys, not tests (they get enough
  of those). Reset buttons, yes; punishment, no.
- **Touch first** (§2.3), targets ≥ 44 px, and every gesture should do
  something — there is no "wrong" input on a good toy.
- **Multi-touch is magic** for siblings sharing a tablet.
- **Instant legibility**: a 6-year-old won't read the controls panel. The toy
  must teach itself through the first random poke. (Keep the panel for the
  grown-ups.)
- **`prefers-reduced-motion`**: check it and tone down shake/strobe effects.
  Avoid full-screen flashing in general (photosensitivity).
- **Sound off by default** inside an app used in classrooms; a big friendly
  mute-state toggle if you add ZzFX.
- **Cap session chaos**: children will spawn the maximum of everything
  instantly. Make the max the *designed* state, not a degraded one.

---

## 8. Idea gallery

Concrete toys, each pairing techniques from above. Roughly ordered by effort.

| Toy | Recipe | Why it's special |
|---|---|---|
| **Jelly buddies** | Soft-body pressure blobs (§3.1) + squash/stretch + googly eyes + pentatonic pops (§5) | Poking a wobbling creature that reacts is peak child joy; eyes turn physics into character |
| **Pond** | 1D heightfield water (§3.10) + buoyant verlet ducks + rain particles | Ripples + floating objects = a complete sensory toy in ~150 lines |
| **Goo lamp 2.0** | Blur+contrast metaballs (§4.3) + real buoyancy/heat convection + OKLCH palette | Upgrade path for the existing lava lamp: blobs that genuinely merge, split, and rise from heat |
| **Ink garden** | Stable fluids (§3.5a) + dye injection per pointer + domain-warped palette (§4.5) | Finger-painting with living paint; the single most mesmerising sim per line of code |
| **Big dig** | Falling sand with materials (§3.4): sand/water/plant/fire + chunky pixel render (§4.6) | The existing sand game grown into a Noita-like ecosystem toy; emergent stories |
| **Puppet pets** | Verlet chains (§3.1) + spring follower head (§3.2) + hand-drawn wobble render (§4.7) | Drag a creature that slinks and settles; IK-free but feels like animation |
| **Firefly field** | Boids with perception cones (§3.6) + glow sprites + trails (§4.2) + synchronised blinking (Kuramoto-style: each firefly nudges its phase toward neighbours) | Emergent synchronisation is genuinely magical to watch happen |
| **Splash bath** | Clavet SPH water (§3.5b) + goo render (§4.3) + pourable containers from static line colliders | Real splashable water; the liquid_pour game's final form |
| **Shadow maze** | Raycast visibility polygon (§4.8) + darkness + hidden glowing collectables | Sight-and-light is an unforgettable effect almost nobody ships |
| **Particle life zoo** | 4–6 particle species with an asymmetric attraction matrix + spatial hash (§3.3) | Self-organising "cells" crawl, chase, and reproduce from ~30 lines of rules |
| **Mandala generator** | Kaleidoscope fold (§4.10) applied to *painting*: the pointer draws glowing strokes (§4.2) into a feedback buffer, folded into N mirrored sectors with dispersion fringes; scroll changes the symmetry count | Symmetry makes anyone an artist — every scribble comes out a rose window; the child is generating the content, not just watching it |
| **Reaction-diffusion painter** | Gray-Scott in a fragment shader with ping-pong buffers (§4.9), pointer seeds | Coral/leopard/fingerprint patterns growing under the finger; the flagship "jump to WebGL" project |
| **Wrecking yard** | Verlet boxes (§3.8) + tearable constraints + trauma screenshake + hit-stop (§5) | Pure demolition catharsis; juice showcase |

---

## 9. Reading list

Everything below is free, canonical, and worth the time:

**Physics**
- Glenn Fiedler — *Fix Your Timestep!* and the Game Physics series (gafferongames.com)
- Thomas Jakobsen — *Advanced Character Physics* (the original Verlet-constraints paper; the cloth game already implements it)
- Müller et al. — *Position Based Dynamics* / Macklin et al. — *XPBD*
- Jos Stam — *Real-Time Fluid Dynamics for Games* (GDC 2003 paper); Mike Ash — *Fluid Simulation for Dummies*
- Clavet, Beaudoin, Poulin — *Particle-based Viscoelastic Fluid Simulation* (SCA 2005)
- Maciej Matyka — *How to Implement a Pressure Soft Body Model*
- Craig Reynolds — *Steering Behaviors for Autonomous Characters*
- Randy Gaul — *How to Create a Custom 2D Physics Engine* (tutsplus series)
- Amit Patel — Red Blob Games (redblobgames.com) — interactive explanations of everything spatial

**Art & shaders**
- Iñigo Quilez (iquilezles.org) — *palettes*, *2D distance functions*, *fbm*, *domain warping*; and Shadertoy generally
- The Book of Shaders (thebookofshaders.com) — gentle GLSL from zero
- Nicky Case — *Sight & Light* (ncase.me/sight-and-light)
- lospec.com — curated limited palettes
- Karl Sims — *Reaction-Diffusion Tutorial*

**Feel & design**
- Jan Willem Nijman (Vlambeer) — *The Art of Screenshake* (talk)
- Martin Jonasson & Petri Purho — *Juice it or lose it* (talk)
- Squirrel Eiserloh — *Math for Game Programmers: Juicing Your Cameras* (GDC talk)
- Steve Swink — *Game Feel* (book; the theory behind all of the above)
- easings.net — every easing curve, interactive
- ZzFX (github.com/KilledByAPixel/ZzFX) — tiny inline sound synth
- The Coding Train (Daniel Shiffman, YouTube) + *The Nature of Code* (natureofcode.com) — the friendliest walkthroughs of half the physics in this handbook

---

*Start anywhere. Pick one toy from §8, build it with the engine bones from §2,
and spend the last 20% of the time entirely on §5. That last 20% is where
"a canvas demo" becomes "wait, this is just a web page?"*
