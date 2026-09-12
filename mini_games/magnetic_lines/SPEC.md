# Magnetic Field Lines: design and physics specification

**File owned by:** the SPEC subagent. Later agents (Setup, Physics, Art, Juice, Verify) read this
and patch the game file. Nobody edits this file after the build starts.

**Target file:** `magnetic_lines.html`, one self-contained HTML file, no build step, no libraries,
no assets.

**Technology:** WebGPU. A compute shader evaluates the field. An instanced render pass draws the
needles. WGSL is the shader language. This is fixed by the owner. Do not propose three.js or
WebGL2 as the main path.

**Handbook sections that govern this build:** §0 house standards, §1 philosophy, §2 engine bones,
§3.9 flow fields, §4.9 shaders, §5 juice, §6 performance, §7 small hands, §10 subagent rules.

---

## 0. The toy in one paragraph

The screen is covered in a grid of tiny compass needles. They all point along the local magnetic
field. Move the mouse and the whole field bends, because the cursor itself is a weak magnet. Click
to drop a bar magnet and drag it around. Right-drag to aim it. Right-click to flip its poles. Roll
the wheel to make it stronger or weaker. The needles have inertia, so they swing and settle like
real compasses instead of snapping. Up to eight magnets. Nothing can fail, nothing can break, and
the reset button always puts it back.

---

## 1. The physics

### 1.1 Which field, and the 2D decision

A bar magnet lying flat on a table, seen from above, is a **magnetic dipole whose moment lies in
the plane of view**. We sample the field at points in that same plane, at z = 0.

This matters, so state it precisely: **we do not simplify the 3D dipole formula to get a 2D one.
We use the exact 3D dipole formula, restricted to the plane that contains the dipole moment.** The
restriction is exact, not an approximation, because the formula only ever needs `m` and `r`, and
both lie in the plane. Every vector in the maths below is a `vec2<f32>`, and the algebra is
identical to the 3D case.

Consequence: the field falls off as **1/r³**, and the on-axis field is twice the equatorial field
at the same distance. That is the real bar-magnet behaviour and it produces the iron-filings
picture people recognise.

The alternative would have been the true 2D dipole, the field of an infinitely long magnet
pointing out of the screen, which falls off as 1/r² with a coefficient of 2 instead of 3. It is
also a legitimate choice and it is gentler to make readable. We reject it because it does not look
like a bar magnet and the owner asked for magnets, not line sources. The shader keeps both
reachable through one constant (§1.6) so the choice can be reversed in one line.

### 1.2 The canonical formula

For a point dipole of moment **m** at centre **c**, the field at point **p** is:

```
r  = p - c
r  = |r|                     (scalar magnitude)
n  = r / r                   (unit vector from magnet to sample point)

B(p) = k * ( 3 (m . n) n  -  m ) / r^3
```

`k` is the scale constant (§1.5). `m . n` is the dot product. This is the standard
`B = (mu0 / 4*pi) * (3(m.rhat)rhat - m) / r^3` with all the constants folded into `k`.

Sanity checks, which the Verify agent must confirm numerically:

| Sample position | Expected result |
|---|---|
| On axis, `n` parallel to `m` | `B = k * 2m / r^3`, pointing along `m` |
| Equatorial, `n` perpendicular to `m` | `B = k * m / r^3`, pointing **against** `m` |
| Double the distance | field drops by a factor of 8 |

The equatorial field pointing against `m` is not a bug. It is why field lines loop back around the
outside of a magnet.

### 1.3 What the shader actually evaluates: the two-pole form

A point dipole is wrong in the near field, and the near field is exactly where the player is
looking. The drawn magnet is a bar roughly 120 px long. A point dipole makes every needle converge
on one point in the middle of that bar, which reads as a mistake.

So each magnet is evaluated as **two magnetic poles** (the Gilbert model): a north pole at one end
and a south pole at the other, each producing an inverse-square field.

```
pole at position s with charge q:    B_pole(p) = k * q * (p - s) / |p - s|^3

pN = c + halfLen * dir        (north end)
pS = c - halfLen * dir        (south end)

B_magnet(p) = B_pole(p, pN, +q) + B_pole(p, pS, -q)
```

This is not a different physics. Expand it for `|p - c| >> halfLen` and it becomes the dipole
formula of §1.2 exactly, with

```
m = q * L * dir        where L = 2 * halfLen
```

So the far field is the correct dipole field, and the near field is the correct finite-magnet
field. It costs two pole evaluations instead of one closed-form dipole evaluation. That is about
24 extra floating-point operations per magnet per needle, which is nothing (§6).

**Both functions go in the shader.** `dipoleField` is kept for the cursor probe readout and for the
Verify agent's cross-check against the two-pole result at large `r`. `poleField` is what the grid
uses.

### 1.4 The singularity, and softening

`1/r^3` goes to infinity at `r = 0`, and `n = r/|r|` is a 0/0 NaN at `r = 0`. A single NaN needle
is visible and ugly. Worse, in some drivers a NaN propagates through `normalize`.

The fix is Plummer softening, the same move as handbook §3.7 for gravity: never take the true
distance, take a slightly padded one.

```wgsl
let d    = p - s;
let r2s  = dot(d, d) + EPS2;      // r2s >= EPS2 > 0, always
let inv  = inverseSqrt(r2s);      // 1 / rs
let B    = d * (q * inv * inv * inv);
```

`inverseSqrt` never divides by zero because `r2s >= EPS2`. The direction is `d * inv`, which
shrinks smoothly to the zero vector at the pole instead of exploding. No branch, no NaN, no
`normalize` call.

**Constant: `EPS2 = 64.0` (px²), so `EPS = 8 px`.**

Chosen as roughly `halfLen / 7.5`. It is small enough that the softening is invisible outside the
drawn magnet body, and large enough to cap the peak field at a finite value. With `S = 1`, the
strongest field anywhere is at `rs = EPS * sqrt(2) ≈ 11.3 px` from a pole, where a single pole
gives `k*q / (1.5 * EPS2) ≈ 104` field units. That is inside the drawn bar, so the player never
sees it.

Honest caveat: with softening, the field at the exact centre of a point dipole comes out
antiparallel to `m`, which is not what the inside of a real magnet does. It does not matter here,
because the magnet body sprite covers that region, and because we use the two-pole model where the
interior field is dominated by the two real poles anyway. Do not try to "fix" it.

### 1.5 Units and scaling, so the numbers land in a usable range

Everything is in **CSS pixels**. Not device pixels, not normalised device coordinates. The grid,
the magnet positions, the pole separation, and `EPS` are all CSS pixels. The vertex shader converts
to clip space once at the end.

Field magnitude is in an arbitrary unit, anchored like this:

> **A magnet with strength `S = 1` produces `|B| = 1.0` at 150 px from its centre, on its axis.**

Solving that for the two-pole model with `halfLen = 60 px`:

```
|B|(150 px, on axis) = K * ( 1/90^2 - 1/210^2 ) = K * 1.00781e-4
K = 1 / 1.00781e-4 = 9922.5
```

**Constant: `K_STRENGTH = 1.0e4` (px² per field unit).** The round number gives `|B| = 1.008` at
150 px, which is close enough to 1.0 that nobody will ever notice.

The full pole charge used in the shader is:

```
q = K_STRENGTH * magnet.strength * magnet.polarity
```

`strength` is the player-controlled multiplier, `polarity` is `+1` or `-1`.

Reference table, `S = 1`, `halfLen = 60`, on-axis, `K = 1e4`. These are the numbers the Verify
agent should reproduce:

| Distance from centre | `\|B\|` |
|---|---|
| 80 px (just past the magnet end) | 24.5 |
| 150 px | 1.008 |
| 300 px | 0.0965 |
| 600 px | 0.01134 |
| 1200 px | 0.001396 |

Note that 600 px to 1200 px is a factor of 8.12. The two-pole model recovers the 1/r³ dipole
falloff in the far field, as it must. That check is worth running.

**The dynamic range across one screen is about 4.2 decades at `S = 1`, and about 5 decades once
the strength slider is in play.** Read §5.2 before drawing anything, because this single fact
decides whether the toy looks good or looks broken.

### 1.6 Shader constants, in one block

```wgsl
const K_STRENGTH : f32 = 1.0e4;     // px^2, field scale (§1.5)
const EPS2       : f32 = 64.0;      // px^2, Plummer softening (§1.4)
const DEFAULT_HALF_LEN : f32 = 60.0;  // px, half the pole separation
const B_MIN_LOG2 : f32 = -12.2877;  // log2(2e-4), see 5.2
const B_SPAN_LOG2: f32 = 18.9316;   // log2(1e2) - log2(2e-4)
```

To switch to the true 2D (1/r²) field instead, change `poleField` to divide by `r2s` once instead
of `rs^3`, i.e. use `d * (q * inv * inv)`. Everything else, including the log mapping, keeps
working. Do this only if the owner asks.

---

## 2. Superposition

Magnetic fields add as vectors. Maxwell's equations are linear in **B**, so there is no
subtlety here and no normalisation step:

```
B_total(p) = sum over i of B_magnet_i(p)     +     B_hand(p)
```

`B_hand` is the cursor magnet (§4.1), evaluated with the identical function. It is not special
cased in the shader. It is simply magnet slot index `magnetCount`, appended to the array each
frame.

### 2.1 The cap, and why

**`MAX_MAGNETS = 8`, plus 1 reserved slot for the hand magnet, so the storage array is 9 elements.**

The cap is not a performance limit. At 8 magnets the compute pass uses about 1% of the frame
budget (§6). The reasons are:

1. **Legibility.** Beyond about six dipoles the field is visual mush. The pleasure of this toy is
   seeing structure: the loops around one magnet, the bridge between two opposite poles, the
   X-shaped neutral point between two like poles. Ten magnets destroy all three.
2. **§7, cap session chaos.** Children will click as fast as they can. The maximum must be the
   *designed* state, not a degraded one. Eight magnets arranged badly still looks good.
3. **§0 and §7, every input does something.** The ninth click must not be refused. It **recycles
   the oldest magnet**: the oldest is removed with a shrink animation and the new one spawns under
   the cursor. Clicking always works, forever. There is no "you have too many" message.

### 2.2 Neutral points are a feature

Where two fields cancel, `|B|` goes to exactly zero and the direction is undefined. This happens
between two like poles and it is a real, named thing in magnetostatics.

Do not clamp it away. Three mechanisms already handle it:

- `t` (§5.2) goes to 0 there, so the needles fade almost to nothing.
- The needle inertia spring (§5.4) has no torque applied when `|B| < 1e-4`, so a needle in a null
  region simply holds its last angle rather than flickering.
- The surrounding needles form the classic X pattern, which is genuinely beautiful.

---

## 3. The compute shader design

### 3.1 Passes, per frame

```
[fixed-step loop, §2.1 of the handbook]
  writeBuffer(magnetBuf)          ~288 bytes, cheap, once per step
  writeBuffer(paramsBuf)          48 bytes
  computePass:  field + needle spring integration
[once per frame]
  renderPass:   instanced needles, then magnet bodies, then cursor overlay
```

The field itself has no history. It is a pure function of magnet state, so it could run once per
rendered frame. The **needle inertia spring does have history**, and springs need a fixed timestep
to feel the same on every machine (handbook §2.1). So the compute pass runs once per fixed 60 Hz
step, inside the `while (acc >= DT)` loop.

On a 144 Hz display most frames take zero steps and every third frame or so takes one. That is
correct: the needles update at exactly 60 Hz and render at 144 Hz. **If zero steps happened, skip
the compute pass entirely and just re-record the render pass.** That is a free performance win on
high-refresh monitors.

### 3.2 Workgroup size

**`@workgroup_size(8, 8, 1)`, giving 64 invocations per workgroup.**

Reasons:

- 64 is a multiple of every common wave/subgroup width: 32 on NVIDIA and Apple, 64 on AMD GCN, 8
  or 16 on Intel. No partial waves.
- It is well inside the `maxComputeInvocationsPerWorkgroup` guaranteed limit of 256.
- The 2D shape matches the 2D grid, so the 8x8 block of needles reads the same magnet array while
  it is hot in cache.

Dispatch:

```js
pass.dispatchWorkgroups(Math.ceil(cols / 8), Math.ceil(rows / 8));
```

The shader **must** bounds-check, because `cols` and `rows` are almost never multiples of 8:

```wgsl
if (gid.x >= P.gridDim.x || gid.y >= P.gridDim.y) { return; }
```

Forgetting this writes past the end of the output buffer. WebGPU clamps out-of-bounds storage
writes rather than crashing, so the symptom is a corrupted first row, not an error message. Watch
for it.

### 3.3 The grid: generated from the invocation id, not stored

There is no positions buffer. Storing 32,400 vec2 positions that never change would be 260 KB of
pointless bandwidth. The cell centre comes from the invocation id:

```wgsl
let cell = vec2<f32>(f32(gid.x), f32(gid.y));
let p    = P.gridOrigin + cell * P.cellPitch;   // CSS pixels
```

JS computes the layout so the grid is centred and symmetric:

```js
const cols   = Math.floor(W / pitch) + 1;
const rows   = Math.floor(H / pitch) + 1;
const originX = (W - (cols - 1) * pitch) * 0.5;
const originY = (H - (rows - 1) * pitch) * 0.5;
```

Flat index, used by both the compute write and the render instance read:

```
i = gid.y * P.gridDim.x + gid.x
```

### 3.4 Buffers

| Buffer | Usage | Contents | Size at max grid |
|---|---|---|---|
| `paramsBuf` | UNIFORM, COPY_DST | one `Params` struct | 48 B |
| `magnetBuf` | STORAGE, COPY_DST | `array<Magnet, 9>` | 288 B |
| `fieldBuf` | STORAGE | `array<vec4<f32>>`, one per cell | 518 KB |
| `stateBuf` | STORAGE | `array<NeedleState>`, one per cell | 259 KB |

`fieldBuf` and `stateBuf` are recreated **only** when the grid dimensions change: on window resize,
or when the player changes grid density with Shift+wheel. Destroy the old ones (`.destroy()`) and
re-seed `stateBuf`.

> **Known trap:** if you resize the grid and forget to re-seed `stateBuf`, the needles inherit
> angles from the previous grid layout and the first few frames look like static. Seed it by
> writing zeros, or better, run one compute step with the spring constant set high so the needles
> snap into place immediately, then drop to the normal constant. The second option has no visible
> pop.

`magnetBuf` is a storage buffer, not a uniform buffer, even though it is tiny. Storage buffers use
the relaxed std430-style layout, which lets the `Magnet` struct pack to 32 bytes with no padding.
In a uniform array it would also work here (32 is a multiple of 16), but storage keeps the rule
simple and leaves room to raise the cap later.

### 3.5 WGSL struct definitions, with the alignment worked out

**This is the section that WebGPU builds get wrong. Every offset below is deliberate.**

```wgsl
// ---- host-shared, storage address space (std430-like rules) ----

struct Magnet {
  pos      : vec2<f32>,   // offset  0   align 8   size 8   centre, CSS px
  dir      : vec2<f32>,   // offset  8   align 8   size 8   unit vector, S -> N
  strength : f32,         // offset 16   align 4   size 4   player multiplier
  halfLen  : f32,         // offset 20   align 4   size 4   half pole separation, px
  polarity : f32,         // offset 24   align 4   size 4   +1 or -1
  spawnAge : f32,         // offset 28   align 4   size 4   seconds since spawn, for juice
};                        // align 8, size 32, array stride 32

struct NeedleState {
  angle : f32,            // offset 0    current rendered angle, radians
  omega : f32,            // offset 4    angular velocity, rad/s
};                        // align 4, size 8, array stride 8

// ---- host-shared, uniform address space (std140-like rules) ----

struct Params {
  @align(16)
  gridDim     : vec2<u32>,  // offset  0   cols, rows
  gridOrigin  : vec2<f32>,  // offset  8   CSS px of cell (0,0)
  cellPitch   : f32,        // offset 16
  magnetCount : u32,        // offset 20   includes the hand magnet
  eps2        : f32,        // offset 24
  logMin      : f32,        // offset 28
  logSpan     : f32,        // offset 32
  dt          : f32,        // offset 36   fixed, 1/60
  viewport    : vec2<f32>,  // offset 40   CSS px, for the vertex shader
};                          // align 16, size 48
```

The rules being obeyed, and the traps being avoided:

1. **`@align(16)` on the first member of `Params` is mandatory, not decoration.** WGSL requires
   a struct in the `uniform` address space to have an alignment that is a multiple of 16. Without
   the attribute, `Params` would take its natural alignment of 8 from `vec2<u32>` and the shader
   module would fail to create, with a validation message that does not obviously say why. The
   total size, 48 bytes, is already a multiple of 16, so no tail padding attribute is needed.
2. **No `vec3<f32>` anywhere in a host-shared struct.** `vec3` has alignment 16 and size 12. Put
   one in a struct and the compiler silently inserts 4 bytes of padding after it, your JS writer
   goes out of step, and the field looks correct in one place and wrong 12 bytes later. If you need
   three floats, use `vec4<f32>` and ignore `.w`, or three separate `f32`s. This is the single most
   common WebGPU bug.
3. **`vec2<f32>` has alignment 8.** An `f32` followed by a `vec2<f32>` leaves a 4-byte hole. In
   `Magnet` the two `vec2`s are deliberately placed first, so the four trailing `f32`s pack tightly
   and the struct comes to exactly 32 bytes with no holes.
4. **Array stride is `roundUp(alignOf(T), sizeOf(T))`.** `Magnet`: `roundUp(8, 32) = 32`.
   `NeedleState`: `roundUp(4, 8) = 8`. Both are already exact, which is why these layouts were
   chosen.
5. **Do not use `bool` in a host-shared struct.** It is not host-shareable in WGSL. `polarity` is
   an `f32` precisely so it can be multiplied straight into `q` with no branch.
6. **Do not use `mat3x3<f32>`.** Its columns are 16-byte aligned, so it occupies 48 bytes, not 36.
   Nothing here needs it.
7. `device.queue.writeBuffer` needs a byte length that is a multiple of 4. All sizes above satisfy
   that. Round buffer allocation sizes up to a multiple of 16 anyway.
8. `minStorageBufferOffsetAlignment` is 256. Only relevant if you use dynamic offsets. Do not.

**JS side.** Write `Params` through a single `DataView` over a 48-byte `ArrayBuffer`, using named
offset constants that match the table above. Do not write it as a `Float32Array` with hand-counted
indices, because `gridDim` and `magnetCount` are `u32` and will come out as garbage floats. Keep
one 288-byte `ArrayBuffer` for the magnets and a `Float32Array` view over it; every `Magnet` field
is an `f32`, so a plain `Float32Array` with stride 8 is safe there.

### 3.6 What the compute pass writes

One `vec4<f32>` per cell:

```
fieldBuf[i] = vec4( dirX, dirY, t, bmag )
```

- `.xy` unit direction of **B**, or `(0,0)` in a null region.
- `.z` the log-mapped strength `t` in `[0,1]` (§5.2). Computed once in compute, not per vertex.
- `.w` the raw `|B|`, kept for the cursor readout and for the Juice agent.

And it updates `stateBuf[i]` in place with the spring integration (§5.4).

`stateBuf` is bound `var<storage, read_write>` in the compute shader. Each invocation reads and
writes only its own element, so there is no race and **no ping-pong buffer is needed**. Say that
out loud because the instinct from fragment-shader work is to ping-pong.

### 3.7 The compute shader body

```wgsl
fn poleField(p: vec2<f32>, s: vec2<f32>, q: f32) -> vec2<f32> {
  let d   = p - s;
  let r2s = dot(d, d) + EPS2;        // softened, always > 0
  let inv = inverseSqrt(r2s);        // 1 / rs
  return d * (q * inv * inv * inv);  // q * d / rs^3
}

// Kept for the cursor probe and for Verify's far-field cross-check.
fn dipoleField(p: vec2<f32>, c: vec2<f32>, m: vec2<f32>) -> vec2<f32> {
  let d   = p - c;
  let r2s = dot(d, d) + EPS2;
  let inv = inverseSqrt(r2s);
  let n   = d * inv;
  return (3.0 * dot(m, n) * n - m) * (inv * inv * inv);
}

@compute @workgroup_size(8, 8, 1)
fn csField(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= P.gridDim.x || gid.y >= P.gridDim.y) { return; }
  let i = gid.y * P.gridDim.x + gid.x;
  let p = P.gridOrigin + vec2<f32>(f32(gid.x), f32(gid.y)) * P.cellPitch;

  var b = vec2<f32>(0.0, 0.0);
  for (var k: u32 = 0u; k < P.magnetCount; k = k + 1u) {
    let m  = magnets[k];
    let h  = m.dir * m.halfLen;
    let q  = K_STRENGTH * m.strength * m.polarity;
    b = b + poleField(p, m.pos + h,  q)
          + poleField(p, m.pos - h, -q);
  }

  let bmag = length(b);
  let dir  = select(vec2<f32>(0.0, 0.0), b / max(bmag, 1e-20), bmag > 1e-9);
  let t    = clamp((log2(bmag + 1e-5) - P.logMin) / P.logSpan, 0.0, 1.0);

  // ---- needle inertia (§5.4) ----
  var st = state[i];
  if (bmag > 1e-4) {
    let target = atan2(dir.y, dir.x);
    var da = target - st.angle;
    da = da - TAU * round(da / TAU);              // shortest way round
    st.omega = st.omega + da * (OMEGA * OMEGA) * P.dt;
  }
  st.omega = st.omega * exp(-2.0 * ZETA * OMEGA * P.dt);
  st.angle = st.angle + st.omega * P.dt;
  state[i] = st;

  field[i] = vec4<f32>(dir, t, bmag);
}
```

`select(falseValue, trueValue, condition)` is the WGSL argument order. Getting it backwards is a
silent bug that blanks the whole grid.

`log2(bmag + 1e-5)` never sees zero, so it never returns `-inf`. `log2(1e-5) = -16.6`, which is
below `logMin` and clamps to `t = 0`. That is the intended behaviour at a null point.

### 3.8 The render pass: instanced needles

One draw call for the whole grid.

```js
pass.setPipeline(needlePipeline);
pass.setBindGroup(0, needleBindGroup);
pass.draw(4, cols * rows);           // topology: 'triangle-strip'
```

Four vertices, one quad, `triangle-strip`, `cullMode: 'none'`. No vertex buffer at all. The vertex
shader builds the corner from `@builtin(vertex_index)` and reads everything else from storage.

```wgsl
@vertex
fn vsNeedle(@builtin(vertex_index) vi: u32,
            @builtin(instance_index) ii: u32) -> VSOut {
  let f  = field[ii];                       // dir.xy, t, bmag
  let st = state[ii];                       // smoothed angle

  let cx = f32(ii % P.gridDim.x);
  let cy = f32(ii / P.gridDim.x);
  let centre = P.gridOrigin + vec2<f32>(cx, cy) * P.cellPitch;

  let len   = P.cellPitch * mix(0.45, 0.95, f.z);   // §5.1
  let wide  = P.cellPitch * 0.26;

  // unit quad corner in needle-local space: x along the needle, y across
  let corner = vec2<f32>(f32(vi & 1u) * 2.0 - 1.0,
                         f32(vi >> 1u) * 2.0 - 1.0);
  let local  = corner * vec2<f32>(len * 0.5, wide * 0.5);

  let ca = cos(st.angle); let sa = sin(st.angle);
  let rot = vec2<f32>(local.x * ca - local.y * sa,
                      local.x * sa + local.y * ca);

  let px  = centre + rot;                                    // CSS px
  var o: VSOut;
  o.pos = vec4<f32>(px / P.viewport * vec2<f32>(2.0, -2.0)
                    + vec2<f32>(-1.0, 1.0), 0.0, 1.0);       // to clip space
  o.uv  = corner;      // [-1,1] both axes, for the SDF
  o.t   = f.z;
  return o;
}
```

Note the `-2.0` and `+1.0` on y. Canvas y goes down, clip space y goes up. Getting this wrong
gives a field that is a perfect mirror image of the correct one, which is very easy to miss,
because a mirrored dipole field still looks like a dipole field. **Verify must check this with a
single magnet whose north pole points up: the needles above it must point away from it.**

The bar-magnet bodies and the cursor overlay are a second, tiny draw call (at most 9 instances)
using the same quad-plus-SDF approach. They draw after the needles so they sit on top.

**Blending:** standard alpha, `src-alpha / one-minus-src-alpha`, premultiplied off. Additive
(`lighter`) is tempting but at 32,000 needles the dense regions saturate to a white blob. If the
Art agent wants glow, add it as a separate low-instance-count pass over the high-`t` needles only.

**Read-only storage in the vertex stage is legal core WebGPU**, so `fieldBuf` and `stateBuf` bind
to the vertex shader as `read-only-storage`. *Writable* storage in a vertex shader is not portable.
The bind group layout entry must be
`{ buffer: { type: 'read-only-storage' }, visibility: GPUShaderStage.VERTEX }`. Because the compute
pass binds the same buffers as `storage` and the render pass binds them as `read-only-storage`,
you need **two bind groups over the same buffers**, not one. Both buffers are created with
`GPUBufferUsage.STORAGE` and that is sufficient for both.

---

## 4. Control mapping

Against §0.1: all four mouse inputs get a distinct, satisfying job. Against §0.2: keyboard is
seasoning only. Against §1.1: the first mouse movement changes the screen, with no click and no
instructions.

| Input | Job | Detail |
|---|---|---|
| **Movement**, no button | **Stir the field.** The cursor is a weak magnet. | Strength 0.35, `halfLen` 30 px. Its axis follows the smoothed direction of mouse travel, so flicking the mouse sweeps the whole field. It never leaves a permanent mark. |
| **Left button** | **Place and drag.** The primary verb. | Press on empty space: a magnet spawns there and is immediately grabbed. Press on an existing magnet: grab it. Drag moves it. Release drops it. The ninth magnet recycles the oldest (§2.1). |
| **Right button** | **Aim and flip.** The second verb. | Right-drag: the nearest magnet rotates so its north end points at the cursor. Right-click with under 6 px of travel: that magnet flips polarity, north and south swap. |
| **Scroll wheel** | **Strength.** The continuous parameter. | Multiplies the nearest magnet's `strength` by 1.12 per notch up, divides by 1.12 per notch down. Clamped to `[0.1, 8.0]`. If no magnet is within 220 px, it changes the hand magnet instead, so the wheel is never dead. |
| **Shift + wheel** | **Grid density.** | `cellPitch` steps through 48, 40, 34, 28, 22, 18, 14, 11, 8 px. Default 22. |

### 4.1 Why these choices

**Movement is the hook (§1.1, §0.1).** A passive "probe that reads the field at the cursor" would
satisfy the letter of §0.1 and none of its spirit. Making the cursor itself magnetic means the
very first mouse move, before any instruction, bends thousands of needles at once. That is the
moment that sells the toy to a six-year-old. §0.1 asks movement to "steer, aim, stir, attract", and
this literally attracts.

Implementation note: when the mouse is still, the velocity direction is undefined. Hold the last
direction and ease toward the new one with the handbook §3.2 exponential ease,
`dir += (target - dir) * (1 - exp(-8 * dt))`, then renormalise. Never let it become a zero vector.

**Left is place-and-drag as one gesture, not two.** Pressing on empty space spawns *and* grabs, so
a single press-drag-release both creates a magnet and positions it. This removes the "I clicked and
nothing moved" dead state. A click with no drag still leaves a magnet, so a random poke always
produces a visible object (§7).

**Right carries two jobs because there are six jobs and four inputs.** The two are separated by
whether the mouse moved, not by a modifier key, which keeps them discoverable by accident. Rotate
is the drag because rotation *is* a dragging motion. Flip is the click because flipping is
instantaneous. Both target the nearest magnet, so right-clicking empty space still does something
(§7: there is no wrong input).

**Strength gets the bare wheel, density gets the modifier.** §0.1 wants "a continuous parameter" on
the wheel. Both candidates qualify, so the tie-break is §1.2: strength changes the *simulation*, so
turning the wheel makes the field visibly bloom or collapse. Density changes the *display*. The
playful one gets the unmodified input. Shift+wheel is a modifier on an existing mouse control, not
a keyboard-gated verb, so §0.2 is respected: no core fun sits behind a key.

Logarithmic wheel steps (x1.12) rather than linear, because the field is logarithmic. Twenty
notches spans the full 0.1 to 8.0 range and every notch produces the same *perceived* change.

### 4.2 Keyboard, optional seasoning only (§0.2)

| Key | Effect |
|---|---|
| `X` or `Delete` | Remove the nearest magnet. |
| `R` | Same as the reset button. |
| `Space` | Pause and unpause the needle spring, freezing the pattern. |
| `H` | Show or hide the controls pane. |

Nothing in this table is required to play.

### 4.3 Mouse wiring, per handbook §2.3

- `canvas.addEventListener('contextmenu', e => e.preventDefault())`. Mandatory, §0.4.
- Read `e.buttons` on `mousemove`, not a hand-rolled `isDown` flag. Bit 1 is left, bit 2 is right.
- Listen for `mouseup` on `window`, not the canvas, so a release outside the window still ends the
  drag.
- `Math.sign(e.deltaY)` on the wheel, with `{ passive: false }` and `preventDefault()`.
- Hit-testing a magnet uses a 40 px radius around its centre or within 30 px of its bar segment,
  whichever is generous. Small hands, §7.

### 4.4 Required chrome

**Controls pane (§0.3).** Fixed top-left, `top: 16px; left: 16px`, dark translucent background,
`backdrop-filter: blur(10px)`, rounded corners, `pointer-events: none`. Lists every control from
the table in §4. Shows live values: magnets `3 / 8`, selected strength `1.8x`, grid `22 px
(87 x 49 = 4263 needles)`, and frame time in ms.

**Reset button (§0.5).** A pill button, `bottom: 24px; left: 50%; transform: translateX(-50%)`.
Removes all magnets, restores `cellPitch` to 22 and hand strength to 0.35, and re-seeds the needle
state. Must be visible, must be clickable, must not be replaced by the `R` key.

---

## 5. Arrow rendering

### 5.1 The needle shape

A plain line segment is **180-degree ambiguous**. It shows orientation but not direction, so a
field pointing north looks identical to one pointing south, and half the physics is lost. The
needle must have a head.

Draw a real compass needle: two triangles back to back, sharing a base, with the front one longer
and warmer.

```
        /|\
       / | \      <- north half, warm, opaque, length 0.62 * len
      /  |  \
     +---+---+    <- shared base, width = wide
      \  |  /
       \ | /      <- south half, cool, dimmer, length 0.38 * len
        \|/
```

Rendered as a signed-distance function in the fragment shader over the instanced quad, using
`o.uv` in `[-1,1]`. Two half-space triangle SDFs, `min`ed together, antialiased with
`fwidth`. SDF gives free antialiasing at any size, which matters because at `cellPitch = 8` the
needle is 8 px long and geometry would alias into noise.

Geometry constants, in units of `cellPitch`:

| Property | Value |
|---|---|
| Total length `len` | `cellPitch * mix(0.45, 0.95, t)` |
| Width at base `wide` | `cellPitch * 0.26` |
| North fraction of length | 0.62 |
| Antialias width | `fwidth(sdf)`, about 1 device pixel |

Note the length range is deliberately **narrow**: 0.45 to 0.95 of the pitch. The weakest needle is
still half the length of the strongest. Encoding five decades of `|B|` in length alone would make
distant needles sub-pixel and invisible, and direction information would be lost exactly where the
player most wants to see the field shape. Length is a hint. Colour and opacity carry the real
signal.

### 5.2 Encoding |B|: the log mapping, and why linear fails

**Read §1.5 first. The field spans about five decades across one screen.**

If `t = |B| / |B|max`, then a needle at 300 px from the magnet has `t = 0.0965 / 24.5 = 0.0039`.
At 600 px it is `0.00046`. Rounded to 8-bit colour, both are **zero**. The result is a bright
smear of needles hugging the magnet and a dead grey screen everywhere else. That is what a first
version looks like when it looks bad, and it is the single most likely failure of this build.

The fix is a fixed logarithmic window:

```wgsl
const B_MIN : f32 = 2e-4;    // below this, fully faded
const B_MAX : f32 = 1e2;     // above this, fully saturated
t = clamp((log2(bmag + 1e-5) - log2(B_MIN)) / (log2(B_MAX) - log2(B_MIN)), 0.0, 1.0);
// => logMin = -12.2877, logSpan = 18.9316   (the §1.6 constants)
```

The window is 5.7 decades wide. `B_MAX = 1e2` is set by the near field of a magnet at the maximum
strength of 8. `B_MIN = 2e-4` is then chosen so that a single magnet at `S = 1` spreads across most
of the range on a 1920x1080 screen. It does:

| Distance | `\|B\|` | linear `t` (wrong) | log `t` (used) |
|---|---|---|---|
| 80 px | 24.49 | 1.000 | 0.893 |
| 150 px | 1.0078 | 0.041 | 0.650 |
| 300 px | 0.09645 | 0.0039 | 0.471 |
| 600 px | 0.01134 | 0.00046 | 0.308 |
| 1200 px | 0.001396 | 0.000057 | 0.148 |

The linear column is the failure mode. Three of its five values round to zero in 8-bit colour. The
log column spreads the same data from 0.15 to 0.89, so every needle on screen sits in a visible
part of the range and the falloff reads as a smooth gradient rather than a cliff.

`log2` is used rather than `log10` or `ln` because it is the native GPU instruction. The choice of
base only changes the constants.

**The window is fixed, not auto-ranged.** Computing the per-frame maximum with a reduction and
normalising to it is tempting and it is wrong here: the whole screen would re-brighten every time
the player drags a magnet near the edge, which is disorienting and destroys the sense that strength
means something absolute. Fixed window, clamped at both ends.

Uncertainty, stated plainly: I have not seen this on screen. `B_MIN = 2e-4` and `B_MAX = 1e2` are
derived from the reference table in §1.5 plus the 8x strength range, not from looking at it. If the
screen reads as too uniform, **narrow** the window (raise `B_MIN`). If the far field is invisible,
**widen** it (lower `B_MIN`). Those two constants are the only tuning knobs the Art agent should
need for this.

### 5.3 Colour and opacity

Background: `#0c1020` with a slow radial gradient to `#05070f` at the corners. Never pure black
(§4.1).

Five-stop ramp, sampled by `t`. Explicit hex stops rather than cosine-palette parameters, because
hex stops can be checked by eye without running the shader:

| `t` | Colour | Reads as |
|---|---|---|
| 0.00 | `#232a52` | deep indigo, barely above the background |
| 0.25 | `#2f6fa8` | steel blue |
| 0.50 | `#35b0b8` | teal |
| 0.75 | `#d9a441` | amber |
| 1.00 | `#fff2d0` | hot near-white |

Opacity: `alpha = mix(0.22, 1.0, smoothstep(0.0, 1.0, t))`. The `smoothstep` keeps the weakest
needles present but quiet, so the far field still shows its shape without competing with the
strong field.

The south half of each needle is the same hue at 55% alpha and 70% luminance, so the needle reads
as directional without introducing a second colour axis that would fight the strength ramp.

Summary of the three readability channels:

| Channel | Encodes |
|---|---|
| Needle **angle** | field direction, exactly |
| Needle **head** (asymmetric shape, brighter front half) | direction sign, removing the 180-degree ambiguity |
| **Colour + opacity**, log-mapped | field strength, five decades |
| **Length**, log-mapped, narrow range | field strength, as a supporting cue only |

### 5.4 Needle inertia, the constant that makes it feel real

Real compass needles have moment of inertia and damping. They swing past and settle. Snapping
instantly to the field looks computed. Swinging looks alive.

Handbook §3.2, applied to the angle, integrated in the compute shader at the fixed 60 Hz step
(§3.7):

```wgsl
const OMEGA : f32 = 14.0;   // rad/s, responsiveness
const ZETA  : f32 = 0.55;   // damping ratio, under 1 so it overshoots
const TAU   : f32 = 6.28318530718;
```

`ZETA = 0.55` is deliberately under-damped. A needle takes about 0.45 s to settle and overshoots by
roughly 17% on the first swing. Dragging a magnet across the screen produces a visible wave of
needles chasing it, which is the best single effect in the toy.

Angle difference must be wrapped to `[-pi, pi]` before it is used as a torque, otherwise a needle
whose target crosses the `+pi / -pi` seam spins all the way round the long way. The
`da - TAU * round(da / TAU)` line in §3.7 does this.

### 5.5 The magnet body

Each magnet draws as a rounded bar, `2 * halfLen` long by 30 px wide. North half `#e8443a`, south
half `#3a7ae8`, with a white `N` and `S` drawn as simple SDF glyphs or as two small shapes. A
6-year-old must be able to see which end is which without reading the controls pane (§7, instant
legibility). Bar width scales slightly with `strength`, from 26 px at 0.1 to 38 px at 8.0, so the
wheel has a visible effect on the object as well as on the field.

---

## 6. Performance target

Per handbook §6. Frame budget 16.6 ms.

**Target: 60 fps at 32,400 needles (`cellPitch = 8` on a 1920x1080 CSS viewport), with 8 magnets
plus the hand magnet, at `devicePixelRatio` capped to 2.**

**Default on load: `cellPitch = 22`, giving 87 x 49 = 4,263 needles.** That is the state the player
sees first and it is chosen for legibility, not for performance.

Arithmetic budget:

| Cost | At the maximum grid |
|---|---|
| Compute invocations | 32,400 |
| Pole evaluations | 32,400 x 9 magnets x 2 poles = 583,000 |
| Compute FLOPs | about 7 MFLOP per step |
| Needle fragments | 32,400 quads x (16 x 8 device px) = 4.1 Mfrag, under one full-screen pass at 1080p/DPR2 |
| Buffer traffic per frame | 288 B magnets + 48 B params uploaded; 777 KB of storage read by the render pass |
| Draw calls | 3 (needles, magnet bodies, cursor overlay) |

**The compute pass is not the bottleneck and will not become one.** Even at the maximum it is
single-digit percent of a frame on integrated graphics. If the toy drops frames, the cause is
fragment overdraw or per-frame JavaScript allocation, not the physics. Diagnose in that order
(§6.1, measure first: script-bound and paint-bound have disjoint fixes).

Rules that must hold, per §6.2:

- **Zero buffer creation in the frame loop.** Create `fieldBuf` and `stateBuf` only on resize or
  density change. Create bind groups at the same time, not per frame.
- **Zero allocation in the frame loop.** Reuse the `Params` `ArrayBuffer` and the magnet
  `Float32Array`. Do not build template strings per frame; update the controls pane text at most
  4 times per second, not every frame.
- Cap DPR at 2 (§2.2).
- Pause on `visibilitychange`, and clamp the accumulator to 0.1 s (§2.1).

**Stated plainly: these are arithmetic budgets, not measurements. I have not run this.** The Verify
agent must measure real frame times at `cellPitch = 8` with 8 magnets and report the number. If the
maximum density does not hold 60 fps, raise the minimum pitch to 11 px (17,000 needles) rather than
reducing the default.

---

## 7. Build order

Five agents, in this order. Handbook §10 governs all of them: **you own one aspect, you patch the
file, you never rewrite it, and you stop when your aspect is done.**

### 7.1 Setup

Create `magnetic_lines.html` as a single self-contained file. Get WebGPU running end to end with
placeholder content. That means: request adapter and device with a clear, friendly on-page message
if `navigator.gpu` is missing or the adapter request fails (never a blank page); configure the
canvas with `navigator.gpu.getPreferredCanvasFormat()` and `alphaMode: 'opaque'`; DPR-aware sizing
capped at 2 (§2.2) with a resize handler; the fixed-timestep loop from §2.1 with the accumulator
clamp; all four mouse events wired per §4.3 including the `contextmenu` preventDefault; the
controls pane and the reset button as DOM elements per §0.3 and §0.5; all four buffers created at
the sizes in §3.4; both bind group layouts; a compute pipeline and a render pipeline that compile
and run. The placeholder compute shader writes `vec4(1, 0, 0.5, 1)` to every cell, so every needle
points right at mid strength. The placeholder needle is a plain rectangle.

**Must not:** write any field maths, choose any colour beyond the background, add particles, sound,
or animation. A Setup task that leaves the needles all pointing right is a success.

### 7.2 Physics

Own everything in sections 1, 2, and 3 of this document. Write `poleField`, `dipoleField`, the
superposition loop, the softening, the log mapping into `t`, and the needle spring integration in
the compute shader. On the JS side: the magnet data model, the `Float32Array` packing that matches
the `Magnet` struct byte for byte, the hand magnet appended as the last array element every step,
the place / drag / rotate / flip / strength operations from §4, the 8-magnet FIFO recycle, and the
buffer re-creation and re-seed when the grid changes. Use the exact constants from §1.6, §5.2 and
§5.4. Verify the §1.5 reference table by reading back one row of `fieldBuf` before declaring done.

**Must not:** change the render pipeline's appearance, choose colours, alter the needle SDF, add
juice effects, or restructure the frame loop. The needles may still be plain rectangles when you
finish.

### 7.3 Art

Own section 5.1, 5.3 and 5.5. Write the needle SDF in the fragment shader, the five-stop colour
ramp, the opacity curve, the background gradient, the magnet body rendering with N and S markings,
and the controls pane CSS (frosted glass, §0.3) and reset button styling (§0.5). Tune only two
physics-adjacent constants if the screen reads badly: `B_MIN` and `B_MAX` in §5.2.

**Must not:** change `K_STRENGTH`, `EPS2`, the field formulas, the spring constants, the control
mapping, or the buffer layouts. If the field looks wrong rather than ugly, report it, do not fix
it.

### 7.4 Juice

Own handbook §5 applied to this toy. Spawn pop-in: a magnet scales from 0 with `easeOutBack` over
about 220 ms, driven by `spawnAge`. Polarity flip: a 180-degree spin of the bar over 180 ms rather
than an instant swap. Recycle: the oldest magnet shrinks out over 150 ms. The cursor: a soft glow
sprite plus a short trailing streamer of past positions. A live field-line trace through the
cursor, integrated by stepping along **B** with RK2 for about 60 steps each way, drawn as a thin
bright curve, so the player sees an actual field line. Sound off by default with a visible mute
toggle (§7), pentatonic pops on spawn and flip if you add it. Check `prefers-reduced-motion` and
tone down the trace and the cursor glow when it is set. Tune `OMEGA` and `ZETA` (§5.4) by eye.

**Must not:** touch the field maths, the control mapping, the buffer layouts, or the colour ramp.
No screen shake in this toy: the field is a calm thing and shaking it would fight the physics.

### 7.5 Verify

Check against §0 point by point: four distinct mouse jobs, controls pane top-left with live values,
reset button bottom-centre that fully restores the initial state, `contextmenu` suppressed,
no touch code. Then check the physics numerically: read back `fieldBuf` with a staging buffer and
confirm the §1.5 reference table to within 1%; confirm the far-field 1/r³ ratio of 8.0 between
600 px and 1200 px; confirm `dipoleField` and the two-pole sum agree to within 2% at 600 px;
confirm no NaN anywhere with the cursor sitting exactly on a magnet centre. Check the y-flip with
the §3.8 test: one magnet with north pointing up, needles above it must point away from it.
Measure frame time at `cellPitch = 8` with 8 magnets and report the number. Confirm the log mapping
shows visible variation at both the near and far extremes. Test resize and density change for stale
`stateBuf` garbage.

**Must not:** redesign anything, retune colours, or add features. Fix only what is broken, in the
smallest possible patch, and report everything else.

---

## 8. Open questions and stated uncertainties

These are genuine unknowns, not placeholders. Do not invent confidence about them.

1. **`B_MIN = 2e-4` and `B_MAX = 1e2` have not been seen on screen.** The values in §5.2 are
   derived from the §1.5 arithmetic and checked numerically, but not visually. They are the most likely thing to need adjusting. Art owns that adjustment.
2. **`OMEGA = 14.0` and `ZETA = 0.55` are a reasoned starting point, not a measured one.** At very
   high needle density the collective wave may read as sluggish. Juice owns the tuning.
3. **`EPS = 8 px` only matters where the magnet art covers it.** If the magnet body is drawn
   narrower than 16 px, the softened region may become visible near the poles.
4. **WebGPU availability on the target machine is unconfirmed by me.** `wgpu-probe.html` exists in
   the scratchpad for this. Setup must handle absence gracefully regardless.
5. **The 60 fps figure at 32,400 needles is arithmetic, not a benchmark.** See §6.
6. **Field-line tracing through the cursor (§7.4) may be better on the CPU than in a shader.** 120
   RK2 steps per frame on the CPU is trivial and avoids a second compute pass and a readback.
   That is my recommendation, but Juice may find the readback path cleaner.
