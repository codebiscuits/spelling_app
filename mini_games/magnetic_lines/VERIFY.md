# VERIFY.md — audit of `magnetic_lines.html`

Read-only review. Nothing in the game file was changed.

**Headline verdict: PARTIAL PASS.** The engine, the physics and the render path are sound.
The file starts cleanly in headless Chrome with no WebGPU validation errors. One house
standard is genuinely broken: the controls pane describes controls the code does not have.

---

## A. Handbook §0 house standards

| # | Rule | Verdict | Note |
|---|---|---|---|
| 1 | Mouse-first, four distinct jobs | **PASS** | All four wired and all four do different things. See table below. |
| 2 | Keyboard is optional seasoning | **PASS** | Only `X`/`Delete` (remove nearest) and `R` (reset). No core fun behind a key. |
| 3 | Controls pane lists what the code does | **FAIL** | The pane still carries the Setup agent's placeholder text. Details below. |
| 4 | No touch support, `contextmenu` suppressed | **PASS** | No touch handlers anywhere. `contextmenu` preventDefault on canvas (line 427) and window (428). |
| 5 | Reset button, bottom-centre pill, full restore | **PARTIAL** | Correct CSS and correct sim reset. Live juice rings survive it. |

### A1. The four mouse jobs (PASS)

| Input | What the code actually does | Where |
|---|---|---|
| Movement | The cursor is a weak magnet (`strength 0.35`, `halfLen 30`). Its axis eases toward the direction of travel, so a flick sweeps the whole field. | `update()` lines 1501-1516 |
| Left button | Press on empty space spawns a magnet **and** grabs it. Press on an existing magnet grabs that one. Drag moves it on a spring. | `mousedown` line ~460, `update()` 1517-1535 |
| Right button | Drag over 6 px aims the magnet's north end at the cursor. Click under 6 px flips it. | `update()` 1537-1565 |
| Scroll wheel | Magnet strength, x1.12 per notch, clamped `[0.1, 8.0]`. Falls through to the hand magnet past 220 px, so it is never dead. | `update()` 1573-1595 |
| Shift + wheel | Grid density through the nine-step pitch table. | line 1575-1576 |

Each is distinct and each is satisfying. Rule 1 passes on substance, not just on presence.

### A2. Controls pane drift (FAIL) — the most important finding

The pane markup at lines 254-267 was never updated after the Setup agent wrote it. The
frosted-glass styling, the position (`top: 16px; left: 16px`) and `pointer-events: none`
are all correct. The **text is wrong**:

| Pane says | The code does |
|---|---|
| `Move mouse` -> "probe the field" | The cursor **is a magnet**. It bends the field. It does not probe it. |
| `Left button` -> "place north magnet" | Place **and grab and drag**. There is no north/south choice. |
| `Right button` -> "place south magnet" | Right **never places anything**. It aims on a drag and flips on a click. |
| `Scroll wheel` -> "magnet strength" | Correct. |

Missing from the pane entirely: **Shift + wheel** (grid density), **`X` / `Delete`**
(remove nearest), **`R`** (reset). A player reading the pane would right-click expecting
a second magnet and get a flip instead.

The live-value half is fine: `updateHud()` (lines 2069-2088) writes real numbers into
`hud-magnets`, `hud-grid`, `hud-strength`, `hud-pointer`, `hud-buttons`, `hud-fps`, and
the headless DOM dump confirms it ran (`0 / 8`, `22 px (36 x 23 = 828 needles)`, `1.00x`).
Two smaller points: the three rows still carry the `.todo` CSS class, so their live values
render in the italic grey "unfinished" style; and SPEC §4.4 asked for **frame time in ms**,
the pane shows FPS.

### A3. `reset()` trace (PARTIAL)

`reset()` at line 782 correctly clears: `state.time`, `state.magnets` (length 0, which
takes every per-magnet juice field with it: `spawnAge`, `flipT`, `flipFrom`, `flipSign`,
`strengthTarget`), `state.strength`, `state.grab`, `state.rightTarget`, hand strength and
hand target, `state.handAge`, hand direction, both wheel accumulators, `state.pitchIndex`
and `state.cellPitch` back to 22, then `buildGrid()` and `seedNeedleState()`. The needle
spring buffer is genuinely zeroed, so no angle survives. Grid and strength: **correct**.

What survives:

- **Live shockwave rings.** `juiceReset()` (line ~1890) zeroes `juice.trail` and sets
  `juice.restPhase = 0`, but it never walks `juice.rings` to clear `live`. Rings spawned
  before the click keep expanding for up to 0.78 s afterwards.
- `juice.pulse` is **increased** by 0.35 rather than zeroed.
- `juice.calm`, `juice.hoverK`, `juice.hoverR` and the cursor spring (`cx, cy, cvx, cvy`)
  are not touched.
- `juice.t` is not reset, so the aurora keeps its phase.

The aurora and cursor spring surviving is defensible: they are ambient and continuous.
The in-flight rings are not. §0 rule 5 says "exactly as if freshly launched". A
`for (r of juice.rings) r.live = false;` in `juiceReset()` would close it.

---

## B. Correctness checks

### B1. The §1.5 reference table — independently recomputed

Reimplemented the spec's own two-pole formula in Python. `K = 1e4`, `halfLen = 60`,
`S = 1`, on-axis, softened with `EPS2 = 64` exactly as `poleField` does.

| Distance | SPEC §1.5 says | **True value, EPS2 = 64** | Unsoftened (EPS2 = 0) | Error in spec |
|---|---|---|---|---|
| 80 px | 24.5 | **19.503** | 24.4898 | **-20.5%** |
| 150 px | 1.008 | **0.99381** | 1.00781 | -1.41% |
| 300 px | 0.0965 | **0.096219** | 0.096452 | -0.29% |
| 600 px | 0.01134 | **0.011330** | 0.011336 | -0.05% |
| 1200 px | 0.001396 | **0.0013962** | 0.0013963 | -0.01% |

**The Physics agent's report is correct, and the problem is slightly wider than reported.**
The whole spec table is the **unsoftened** table, not one bad row. It happens to agree
within 1.4% from 150 px outward, because softening is negligible once `r >> 8 px`. At
80 px the sample sits 20 px from the near pole, where the +64 px² in the denominator is
14% of `r²`, and the published 24.5 is 20.5% high. The shader is right; the table is
wrong. **Nothing in the code needs changing.**

Knock-on: SPEC §5.2's worked example uses 24.49 as `|B|max` for the "linear t fails"
argument. The argument is unaffected — the failure it demonstrates is far larger than 20%.

**1/r³ falloff at distance — holds.**

| Span | Measured ratio | Ideal for 2x |
|---|---|---|
| 80 -> 150 px | 19.62 | 8.0 (near field, correctly not dipole) |
| 150 -> 300 px | 10.33 | 8.0 |
| 300 -> 600 px | 8.49 | 8.0 |
| 600 -> 1200 px | **8.118** | 8.0 |

SPEC §1.5 predicted 8.12 for the last row. Confirmed to three digits.

**Dipole cross-check (SPEC §7.5 asked for 2% at 600 px):** with `m = q*L*dir = 1.2e6`,
`dipoleField` gives 0.011105 against the two-pole 0.011330, a **1.99% difference**. It
passes, but only just. At 1200 px it is 0.50%; at 300 px it is 7.8%.

**Sign and ratio checks (SPEC §1.2):** at (300, 0) with `m` along +x the field is
`(+0.0962, 0)`, along `m`. At (0, 300) it is `(-0.0419, 0)`, **against** `m`, as
magnetostatics requires. On-axis / equatorial ratio is 2.298 at 300 px, tending to the
textbook 2.0 in the far field. Correct.

**NaN check:** field at the exact north pole (60, 0) is `(-0.690, 0)`; at the exact
centre (0, 0) it is `(-5.411, 0)`. Both finite. Softening works.

**Log mapping:** recomputed `t` from the true softened values gives 0.875 / 0.649 / 0.471
/ 0.308 / 0.149 across 80-1200 px. Matches SPEC §5.2's column to two decimals and spreads
the full screen across a visible range. The mapping is fine.

**y-flip (SPEC §3.8):** `toClip` at line 1154 is
`vec4(x/W*2 - 1, 1 - y/H*2, 0, 1)`. The y term is inverted exactly once. **PASS.**

### B2. Flip semantics — nothing is broken, one stale read

The Juice agent's change is correct physics. Rotating `dir` by π swaps which end carries
`+q`, which is algebraically identical to negating `polarity`. Every reader of `polarity`
was checked:

| Site | Reads polarity as | Still correct? |
|---|---|---|
| Compute shader line 1018, `q = K_STRENGTH * m.strength * m.polarity` | scalar sign on the pole charge | **Yes.** `q` stays `+K*S`; the poles move instead. |
| `vsMagnet` line 1323, `o.g = vec4(hlen, hwid, m.polarity, 0)` | packs it for the fragment stage | Yes, passthrough. |
| `fsMagnet` line 1334-1348, `side = smoothstep(-1.2, 1.2, o.lp.x * pol)` and the N/S glyph placement | which local end is north | **Yes.** `pol` is now always +1, so north is always local +x, which is the direction `dir` points. The colours and glyphs ride the rotating bar correctly. |
| JS line 744, `magnetData[o + 6] = m.polarity` | buffer packing | Yes. |
| **JS line 631, `m.flipSign = -m.polarity`** | "which way round it turns" | **No.** See below. |

**Defect (low).** `startFlip()` sets `flipSign = -m.polarity`. Under the old semantics
`polarity` alternated, so consecutive flips spun opposite ways and the comment
"alternates, so repeats unwind" was true. `polarity` is now permanently `+1` — nothing in
the file ever writes it, and `makeMagnet` is only ever called with `1` (line 653) — so
`flipSign` is always `-1` and every flip spins the same direction. The bar still lands
correctly (line 645-646 snaps `dir` to the exact reverse), so this is cosmetic: repeated
flips wind up rather than unwind. The comment is now false.

Related, informational: `polarity` is effectively a **dead field**. It is still declared
in the WGSL struct, still packed into the 32-byte stride, and still multiplied into `q`,
but it can only ever be `+1`. Leave the struct alone (the layout is load-bearing), but a
reader will assume it does something.

### B3. Vertex shader reads the spring — PASS

`vsNeedle` line ~1196: `let ang = state[ii].angle;` with the comment "§5.4: the SPRING
angle, never atan2". It reads `field[ii].z` only for `t` (length and colour). There is no
`atan2` anywhere in the render module. The inertia effect is intact.

### B4. Bind group is never cached across frames — PASS

`gpu.renderBindGroup` is created only inside `allocGridBuffers()` (line 1469), which runs
only from `buildGrid()` when `cols` or `rows` change, or when `gpu.fieldBuf` is null.
`render()` reads it into a local at line 1706 **inside the function body**, so it is
re-read every frame. No module-level cache, no closure capture. Buffer destroy ordering is
correct: old buffers are destroyed at 1445-1446 and the new bind groups are built from the
new ones before anything can draw.

### B5. WGSL reserved keywords — PASS

Scanned both shader modules for the WGSL reserved-word list used as identifiers. No
collisions remain beyond the `target` the Physics agent already renamed; the compute
shader now has no `target` binding at all. The headless run confirms both modules compile:
the fallback panel never gets its `show` class.

---

## C. Robustness

**Fallback path (PASS, structurally).** Line 841 guards `if (!('gpu' in navigator) || !navigator.gpu)` before any other GPU call and calls `showFallback()` with a specific reason. Four further failure points are each handled with their own message: `requestAdapter()` throwing (850), returning null after a `forceFallbackAdapter` retry (857-865), `requestDevice()` failing (876) or returning nothing (881), and `getContext('webgpu')` returning null (887). Both pipeline creations are wrapped in `pushErrorScope('validation')` and route a failure to the same panel (1099, 1398). The whole startup is wrapped in a try/catch (2168). This is the best-handled part of the file.

**Softening on every path (PASS).** `EPS2` is added in `poleField` (line 988) and in `dipoleField` (997). Those are the only two field evaluations in the entire file — there is no CPU-side field maths, so there is no unsoftened path to miss. `dir` is additionally guarded by `select(vec2(0), b / max(bmag, 1e-20), bmag > 1e-9)` (1025) and the torque is gated on `bmag > 1e-4` (1031), which is the intended null-point behaviour from SPEC §2.2. All four fragment shaders divide by `max(fwidth(d), 1e-4)`. The JS normalisations at 1513 and 1549 are guarded. No division by zero anywhere.

**Per-frame allocation (PASS, with one honest caveat).** Scanned `update()` and `juiceDraw()` (lines 1490-2060): no `new`, no array methods that allocate, no template literals. The ring pool is 40 preallocated objects and `addRing()` reuses slots. The cursor trail is one `Float32Array` built once. `updateHud()` builds strings but is throttled to four times a second. `magnetData` and `paramsBytes` are reused buffers. The caveat: `render()` allocates a command encoder, a render-pass descriptor object with a nested array, and a texture view every frame. That is unavoidable in the WebGPU API and every WebGPU app does it. Separately, `seedNeedleState()` allocates a zero-filled `Uint8Array` up to 259 KB — not in the hot loop, but a fast Shift+wheel spin triggers one per notch.

**Magnet cap (PASS on behaviour, PARTIAL on spec).** `addMagnet()` line 651: `if (state.magnets.length >= MAX_MAGNETS) state.magnets.shift();` then push. The ninth click is never refused, the oldest goes, and the new one spawns under the cursor and is grabbed. Three stale-index paths are all guarded: `update()` clears `state.grab` if it is past the end (1519), clears `state.rightTarget` likewise (1539), and `juiceDraw()` bounds-checks `juice.hoverIdx` (2032-2033). The shader draws `MAGNET_SLOTS` instances and collapses unused ones in the vertex stage, so a shorter list cannot leave a ghost bar. **The gap:** SPEC §2.1 and §7.4 asked the recycled magnet to **shrink out over 150 ms**. `shift()` removes it instantly. Functionally correct, less juicy than specified.

---

## D. Headless run

```
timeout 90 google-chrome --headless=new --enable-unsafe-webgpu --enable-features=Vulkan \
  --virtual-time-budget=9000 --dump-dom ".../magnetic_lines.html"
```

**Result: clean.** The grep returned 11 `error` and 5 `validation` hits, which is **exactly
the count of those two words in the source file itself** (`pushErrorScope('validation')`,
the fallback strings, the catch handlers). Baseline-subtracted, the run produced **zero**
runtime errors, zero Tint messages and zero validation failures. Chrome's stderr was 11
lines, none matching tint/wgsl/validation/shader.

Decisive evidence that WebGPU started and ran:

- `<div id="fallback">` came back with **no `class` attribute**, so the fallback panel was
  never shown. Every failure path in the file adds a class to it.
- The HUD carries live values that only `updateHud()` can write:
  `hud-magnets` = `0 / 8`, `hud-grid` = `22 px (36 x 23 = 828 needles)`,
  `hud-strength` = `1.00x`.

`hud-fps` reads `--`, because `--virtual-time-budget` does not advance the wall clock the
FPS sampler uses. That is a harness artefact, not a defect.

---

## Defects, by severity

| # | Sev | Defect | Where |
|---|---|---|---|
| 1 | **High** | Controls pane text describes controls that do not exist. Left is not "place north", right is not "place south", movement is not "probe". Shift+wheel, `X`/`Delete` and `R` are missing from the pane. Breaks §0 rule 3. | lines 254-267 |
| 2 | **Medium** | `reset()` leaves live shockwave rings running and bumps `juice.pulse` instead of zeroing it. §0 rule 5 wants the freshly-launched state. | `juiceReset()`, ~1890 |
| 3 | **Medium** | SPEC §7.4's live RK2 field-line trace through the cursor is not implemented. Zero matches for `rk2`/`fieldline`/`trace` in the file. | absent |
| 4 | **Low** | SPEC §4.2 keys `Space` (pause) and `H` (hide pane) not implemented. Only `X`/`Delete` and `R`. Not a §0 breach, keyboard is seasoning. | keydown handler |
| 5 | **Low** | Magnet recycle is an instant `shift()`. SPEC §2.1/§7.4 asked for a 150 ms shrink-out. | line 652 |
| 6 | **Low** | `m.flipSign = -m.polarity` is a stale read of the old flip semantics. `polarity` is now frozen at +1, so every flip spins the same way and the "repeats unwind" comment is false. | line 631 |
| 7 | **Low** | `polarity` is a dead field: never written, only ever +1, still occupying the GPU struct. | 608, 744, 1018 |
| 8 | **Cosmetic** | `.todo` placeholder class still on the Magnets / Grid / Strength rows, so three live values render in italic grey "unfinished" styling. | 261-263, CSS 128 |
| 9 | **Cosmetic** | Pane shows FPS; SPEC §4.4 asked for frame time in ms. | 2069 |
| 10 | **Cosmetic** | Two `wheel` listeners on the canvas, one passive (reads `shiftKey`), one not (preventDefault + accumulate). Works, but one would be clearer. | ~1466 region |
| 11 | **Doc, not code** | SPEC §1.5's reference table is the **unsoftened** table. The 80 px row is 20.5% high; the rest agree within 1.4%. The shader is correct. SPEC is frozen, so this is recorded, not fixed. | SPEC §1.5 |

**Count: 1 high, 2 medium, 4 low, 3 cosmetic, 1 spec-document error.** Nothing critical.
No crashes, no NaN, no validation errors, no broken physics.

---

## What I could not verify, and why

1. **Frame time at `cellPitch = 8` with 8 magnets.** SPEC §6 and §7.5 both demand a real
   number. I have no way to get one: the WebGPU canvas does not composite into headless
   Chrome in this environment, and there is no timing instrumentation in the file that
   survives to the DOM. The FPS readout exists but needs a real window. **The owner should
   press Shift+wheel down to 8 px, place 8 magnets, and read the FPS row himself.** If it
   drops below 60, SPEC §6 says raise the minimum pitch to 11 px, not lower the default.
2. **Anything visual.** The colour ramp, whether `B_MIN = 2e-4` and `B_MAX = 1e2` read well
   on screen, whether the needle head resolves the 180-degree ambiguity at small pitch,
   whether the aurora is too strong. SPEC §8.1 flags these as the most likely things to
   need tuning and they need eyes. The owner has confirmed the file renders; he has not
   confirmed it looks right.
3. **`fieldBuf` readback.** SPEC §7.5 asked for a staging-buffer readback to confirm the
   reference table on the GPU. I could not run a GPU readback headless. I verified the same
   maths in Python against the shader source line by line instead, which catches a wrong
   formula but would not catch a buffer-layout bug. The layout was audited by eye and
   matches SPEC §3.5 byte for byte.
4. **Live interaction.** Drag feel, whether the spring weight on a grabbed magnet reads as
   weight or as lag, whether the flip spin is legible at 180 ms, whether `OMEGA = 14` and
   `ZETA = 0.55` feel right. All of §5 needs a hand on a mouse.
5. **Resize and density-change stale state under real load.** I traced the code path and it
   is correct (buffers destroyed, bind groups rebuilt, `stateBuf` re-zeroed). I could not
   drive an actual resize to confirm no frame slips through between the destroy and the
   rebuild.
