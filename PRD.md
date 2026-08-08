# Stitchery — Photo/Pattern → Embroidery File Web App

*PRD + tracer-bullet implementation plan*

---

## 1. Summary

A web app that turns an uploaded image (line art, logo, or simple pattern) into a
machine-ready embroidery file — primarily PES for a Brother VE2300, with other
formats as a near-free bonus. The user uploads, reduces the image to a small set of
thread colours, previews the actual stitches, and downloads a file to put on a USB
stick. Built as a genuinely-owned app around two borrowed algorithmic engines, and
intended to double as a portfolio piece.

## 2. Problem & goal

Digitizing (image → stitches) is normally manual, expensive, or locked in desktop
software. **Goal:** a self-serve web tool that produces a *good-enough, cleanly-sewing*
embroidery file for simple inputs, with a stitch-accurate preview so the user knows
what they'll get before committing thread to fabric.

**Explicit non-goal:** professional-grade photo embroidery ("thread painting"). Full
colour photos degrade badly through auto-digitizing; they are out of MVP scope and, if
allowed at all, are clearly marked best-effort.

## 3. Users

- **Primary:** a home embroiderer (Brother VE2300, 8"×12" / 200×300mm max hoop) who
  wants to stitch a logo, drawing, monogram, or clean pattern without learning
  digitizing software.
- **Secondary:** portfolio audience — the app should *look* and *feel* impressive,
  which is why the stitch preview is a first-class feature, not an afterthought.

## 4. Scope

**In scope (MVP):**
- Upload PNG/JPEG.
- Crop/scale to hoop, with hard bounds at 200×300mm.
- Perceptual colour reduction to N colours, snapped to a real thread palette.
- Raster → vector tracing.
- Fill (and basic stroke) stitch generation via Ink/Stitch.
- Stitch-accurate preview in the browser.
- Download PES.

**In scope (fast follow, cheap once MVP works):**
- Additional output formats (DST, JEF, VP3, EXP) via a dropdown.
- Density / thread-break warnings surfaced in the preview.

**Out of scope:**
- High-fidelity photo embroidery.
- In-app manual node editing of stitch paths.
- Accounts, saved projects, multi-user anything (until/unless it's public and wanted).

## 5. Success criteria

1. A clean line-art or logo upload produces a PES that sews on the VE2300 without
   thread breaks or obvious defects.
2. The browser preview visibly resembles the sewn result (individual stitches, correct
   thread colours).
3. End-to-end (upload → download) completes in a few seconds for a reasonable image.
4. The whole thing runs from one container, deployable on the Tailscale box today and
   publicly later without re-architecting.

## 6. Architecture

### Borrowed vs. built

| Concern | How | Why borrowed / built |
| --- | --- | --- |
| Raster → vector | **VTracer** (Rust core, Python binding; MIT/Apache) | Curve-fitting + colour clustering is a solved deep problem; MIT license is clean for hosting. |
| Vector → stitches | **Ink/Stitch** (GPL-3.0), as a vendored binary | Fill/satin/underlay/routing is decades of craft; not worth reimplementing. |
| Stitch file encode/decode | **pyembroidery** (pure Python) | Format-agnostic read/write of PES/DST/JEF/VP3/etc. Pure Python → installs in the app venv. |
| Perceptual quantize → thread palette | **Built** | The core embroidery-specific value. Decides thread-change count and result quality. |
| Feature-size cleanup, fill/stroke classification, `inkstitch:` tagging | **Built** | The app's real intellectual work. |
| UI + stitch preview | **Built** | Portfolio centrepiece. |

### One container, one venv + one sealed binary

*Revised after bullet 0 — the original plan assumed a second pinned virtualenv. It isn't
needed.*

Ink/Stitch ships as a **PyInstaller bundle with its own vendored Python 3.11** and its own
copies of numpy, Pillow, lxml, shapely, wx and GTK. There is nothing to pip-install and no
second venv to manage.

- **`.venv`** (modern Python, currently 3.14): FastAPI, upload handling, quantize→palette
  (numpy / Pillow / scikit-image), VTracer trace, `lxml` SVG tagging, **pyembroidery**
  read-back for the preview.
- **Ink/Stitch**: a single ~19MB executable plus its bundle directory, installed as a system
  package. Invoked as a **subprocess**; nothing about it is importable from the app.

The isolation is therefore stronger than planned and free: the 3.11 interpreter, the GPL
code, and its dependency tree are all sealed inside that executable.

### Verified integration facts

Established by hand in bullet 0 — treat these as ground truth, not assumptions.

- **Install:** `inkstitch` 3.2.2 from the AUR. Depends only on `inkscape`. Installs to
  `/usr/share/inkscape/extensions/inkstitch/`, with the executable at `bin/inkstitch`
  (world-executable — no `sudo` needed, and using `sudo` only creates root-owned output).
- **Invocation:** one binary dispatches every extension. The `.inx` files under `inx/`
  declare the contract; `<param>` entries map to `--name=value` flags:

  ```
  /usr/share/inkscape/extensions/inkstitch/bin/inkstitch \
      --extension=output --format=pes design.svg > design.pes
  ```

- **Output goes to stdout as binary.** Always redirect; never decode. Exit code is
  unreliable — validate the *output* (nonzero size, parses as PES, stitch count > 0).
- **`--format=` is a free knob**: `pes`, `dst`, `jef`, `vp3`, `exp`, … same command. Multi-
  format output is a dropdown, not a feature.
- **PES version emitted is 1** (`pattern.extras['version']`). Oldest and most widely
  readable dialect — the best case for an older Brother. No CLI param exposes the version,
  so if the VE2300 rejects v1 the escape hatch is re-encoding from the `EmbPattern` with
  pyembroidery.
- **Units:** an SVG with `width="60mm"` and `viewBox="0 0 60 60"` gives 1 user unit = 1mm,
  and pyembroidery reports coordinates in **tenths of a mm** (a 40mm square reads as bounds
  `(0, 0, 400, 400)`). Exactly ×10, no fudge factors.
- **`inkstitch:*` params are optional for a basic fill.** A plain `<rect>` with `fill` set
  and no Ink/Stitch attributes at all stitches as a fill. Raw shapes work; no
  Object-to-Path needed. Minimal tagging for bullet 1 is therefore "ensure `fill` is set,
  `stroke` is none" — real params become a bullet 4 optimisation.
- **Stroke leaks a thread.** Every filled object becomes its own colour block, so a stray
  shape or a stroked outline silently adds a thread change.
- **No display needed** for the output extension — it ran headless with empty stderr,
  despite the bundle carrying wx/GTK. Extensions with UI (params dialogs, simulator) do
  need X and bundle Flask; avoid those from the server.

### Data flow

```
React SPA
  upload → crop-to-hoop → (optional client preview) → POST image
      │
      ▼
FastAPI (.venv-app)
  validate upload (size / type / dimensions)
  perceptual quantize → thread palette          [numpy / Pillow / skimage]   ← built
  VTracer trace → layered SVG                    [vtracer python binding]     ← borrowed
  tag paths: inkstitch:* params, colours, order  [lxml]                       ← built
      │  subprocess: tagged.svg ───────────────►  bin/inkstitch (vendored 3.11)
      │                                              Ink/Stitch → PES on stdout ← borrowed
      │  ◄─────────────────────  stdout bytes  ──────┘
  read design.pes → stitch-coordinate JSON       [pyembroidery]              ← built glue
  return { previewStitches: [...], pesUrl, warnings }
      │
      ▼
React SPA
  render stitches on <canvas>  ← portfolio centrepiece
  enable Download (format dropdown)
```

### The promotable seam

The subprocess boundary's interface is already **"SVG file in → PES file out."** If you
ever need to isolate the GPL/3.11 blast radius or scale generation independently,
promote that single call from subprocess to HTTP against a separate container — nothing
else changes. Don't pay for that split until something forces it.

### Deployment

- **Dev / private:** single container (rootless Podman / quadlet, like the n8n box) on
  `llama`, reached over Tailscale. No auth, no public attack surface.
- **Public (later):** add upload validation, rate limiting, size caps. Roughly doubles
  the non-feature work — do it only when the portfolio motive actually needs a public URL.

## 7. Key risks & mitigations

| Risk | Mitigation |
| --- | --- |
| **Machine won't read the output** (the least-controllable link) | **Tracer bullet 0:** hand-built PES onto the actual VE2300 *before* building anything upstream. **Still open** — no machine access until the owner is back. Partially derisked: PES v1 is emitted, and the file round-trips through an independent reader (pyembroidery) with correct bounds, thread count and stitch count. Fixture + expected numbers are committed, so the sew is a five-minute check. |
| Photo inputs look terrible | Scope MVP to line art / logos / patterns; mark photos best-effort or reject. |
| GPL-3.0 (Ink/Stitch) contaminating the product | Sealed in a separate executable, called by subprocess; nothing is imported. Hosting a service ≠ distributing a binary. Revisit only if shipping a downloadable bundle. |
| Python 3.11 pin breaking the app | Non-issue: the 3.11 interpreter is vendored inside the Ink/Stitch bundle. App code never sees it. |
| **Dev and prod install different Ink/Stitch artifacts** | Dev uses the Arch/AUR package; the Dockerfile targets Debian and a `.deb` that was never verified. Pick one artifact and use it in both, or you'll debug two Ink/Stitch installs instead of one. |
| "Looks fine on screen, sews badly" | Surface Ink/Stitch density / troubleshoot output as preview warnings (fast-follow). |
| Public upload endpoint abuse | Deferred to the hardening bullet; private-first until then. |

## 8. Implementation plan — tracer bullets

Philosophy: each bullet is a **thin vertical slice that touches every layer end-to-end**,
then later bullets *thicken* individual stages. Never build one layer "fully" in
isolation. Get an ugly-but-complete path working, then improve fidelity.

### Bullet 0 — Prove the pipe (no code, no web)  *[in progress]*

The single most important derisking step. By hand:
1. ~~Author one trivial SVG (a filled 40×40mm rectangle).~~ **Done.**
2. ~~Install Ink/Stitch and run the CLI to produce a PES.~~ **Done** — see *Verified
   integration facts*. Both documented traps confirmed real: binary stdout, unreliable
   exit code.
3. ~~Read the PES back independently and check it.~~ **Done** — pyembroidery reports bounds
   `(0, 0, 400, 400)`, matching the 40×40mm drawn.
4. **Blocked:** put it on a USB stick, sew it on the VE2300.

Committed as a fixture (`rect40.svg` + `rect40.pes`) with expected bounds, thread count and
stitch count recorded alongside, so it doubles as a regression test.

**Sew-day checklist** (one shot, prep in advance):
- Stick carries the fixture PES.
- Written expectations: 40×40mm, 1 thread, known stitch count — so "it sewed" and "it sewed
  *correctly*" are distinguishable.
- Photograph the result next to a ruler; that's the scale check bullet 3 needs.

**Done when:** the machine stitches the rectangle at the right size.

**Sizing lesson worth keeping:** the first attempt was 170×139mm with two colours →
76,487 stitches, a ~2 hour sew. Stitch count scales with *area*. Keep test designs small
and single-colour, or you'll burn an afternoon per iteration.

### Bullet 1 — Walking skeleton (every layer, zero fidelity)

- React: single upload button → POST to FastAPI → render whatever comes back on a canvas
  → download button.
- FastAPI: crude fixed quantization (e.g. naive 4-colour), VTracer with default params →
  SVG, minimal tagging (set `fill`, clear `stroke` — params not required, see bullet 0),
  subprocess → Ink/Stitch → PES on stdout, read back with pyembroidery → stitch-coord JSON,
  return `{ previewStitches, pesUrl }`.
- Subprocess wrapper: capture stdout as bytes, capture stderr separately and log it, enforce
  a timeout, and validate success from the output rather than the exit code.
- Container: Ink/Stitch installed and callable; the subprocess call works.

**Done when:** you upload any simple image and get a downloadable PES plus a rough
on-canvas stitch preview. Output quality irrelevant. **This is the architecture proven.**

### Bullet 2 — Real colour reduction (thicken: quantize + palette)  *[your core value]*

- Perceptual quantization in CIELAB, not RGB.
- Snap each cluster to the nearest real Brother/Madeira thread; expose a thread list.
- User control for N colours (= thread-change count).
- Pre-quantize *before* VTracer so tracing sees flat colour regions, not fringes.

**Done when:** colour count is user-controlled and outputs map to nameable real threads.

### Bullet 3 — Hoop discipline (thicken: crop/scale)

- React crop/scale UI; hard bounds at 200×300mm.
- mm-accurate scaling through the whole pipeline (px ↔ mm is a common bug source).
- Reject / warn on designs that exceed the hoop.

**Done when:** output physical dimensions are correct and hoop-bounded.

### Bullet 4 — Better stitches (thicken: tagging)

- Fill vs. stroke classification per traced region.
- Satin edges where appropriate; running stitch for thin lines.
- Real `inkstitch:*` params: underlay, row spacing/density, fill angle, pull comp.
- Set stitch order via SVG stacking order; add `trim` / `stop` object commands where useful.

**Done when:** outputs sew cleanly (underlay present, sensible density, no obvious defects).

### Bullet 5 — Preview fidelity (thicken: the centrepiece)

- Per-segment thread colours; connect consecutive stitch points as line segments.
- Pan / zoom (free once it's on canvas).
- Subtle per-stitch offset / drop-shadow so it reads as thread.
- Surface density heat-map / thread-break warnings (from Ink/Stitch validation).

**Done when:** the preview convincingly resembles sewn embroidery and flags risky density.

### Bullet 6 — Multi-format output (thicken: encode)

- Format dropdown (PES default; DST as universal fallback; JEF/VP3/EXP).
- Mostly already free: swap the `--format=` value on the same command (confirmed in bullet 0).
  Alternative path is re-writing from the `EmbPattern` you already read back with pyembroidery
  — worth keeping for formats Ink/Stitch handles poorly, or if PES version ever needs forcing.
- **Caveat:** DST doesn't store thread colours natively — don't treat DST round-trips as
  lossless.

**Done when:** the user can pick a format and get a valid file for their machine.

### Bullet 7 — Public hardening + deploy (only if going public)

- Upload validation (type, size, dimension caps), rate limiting.
- Resource limits on the generate subprocess (timeouts; big-image guardrails).
- Public deploy; keep the Tailscale path for private use.

**Done when:** a stranger can't trivially abuse the upload endpoint, and it's live.

## 9. Reference links

- Ink/Stitch command line: https://inkstitch.org/docs/command-line/
- Ink/Stitch params: https://inkstitch.org/docs/params/
- Ink/Stitch workflow: https://inkstitch.org/docs/workflow/
- Ink/Stitch code-level docs (DeepWiki): https://deepwiki.com/inkstitch/inkstitch
- VTracer: https://github.com/visioncortex/vtracer  (Python binding: `vtracer` on PyPI)
- pyembroidery: https://github.com/EmbroidePy/pyembroidery
- Headless-integration reference (read `runner.py` + design notes; don't depend on it):
  https://github.com/GreerBK/InkStitchMCP

## 10. Open decisions (defer until they bite)

- **Trace client-side (VTracer WASM) vs server-side (Python binding)?** Server-side for
  now — trace and tag want to live together. WASM path stays open for a future
  "all-in-browser" story.
- **Read preview from PES (pyembroidery) vs Ink/Stitch `stitch_plan_preview`?** Default to
  reading the PES you already generate; revisit if you want needle-point fidelity Ink/Stitch
  renders directly.
- **Public at all?** If it's genuinely just for one machine, staying on Tailscale removes
  an entire category of work.
