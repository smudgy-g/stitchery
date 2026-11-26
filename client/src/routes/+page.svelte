<script lang="ts">
  import { onMount, untrack } from "svelte";
  import {
    ArrowDown, ArrowUp, ArrowUpRight, Crop, Eye, EyeOff, FlipHorizontal2, FlipVertical2, Image as ImageIcon, ImagePlus,
    ListOrdered, Maximize, Palette, Pencil, Printer, RefreshCw, RotateCcw, RotateCw, Spool, Undo2, WandSparkles,
  } from "@lucide/svelte";
  import { Button } from "$lib/components/ui/button";
  import { Checkbox } from "$lib/components/ui/checkbox";
  import { Input } from "$lib/components/ui/input";
  import { Label } from "$lib/components/ui/label";
  import * as NativeSelect from "$lib/components/ui/native-select";
  import { Slider } from "$lib/components/ui/slider";
  import * as ToggleGroup from "$lib/components/ui/toggle-group";
  import PictureEditor from "$lib/PictureEditor.svelte";
  import StitchPreview from "$lib/StitchPreview.svelte";
  import ThreadPicker from "$lib/ThreadPicker.svelte";
  import {
    getMachines, getThreads, inches, makeColours, makeStitches, removeBackground, saveFile,
    type Design, type FillMethod, type Machine, type StitchSettings, type Thread,
  } from "$lib/api";
  import { loadColours, paint, toPng, type Swatch } from "$lib/colours";
  import { decode, exportPicture, fit, fits, load, NO_ADJUST, pxPerMm, replaceImage, size, toBlob, type Picture } from "$lib/picture";

  const TYPES = ["image/png", "image/jpeg", "image/webp"];
  // Below this the picture has less detail than a stitch can show, so fills come out blocky
  const MIN_PX_PER_MM = 4;
  // ponytail: a typical home machine speed; real time varies with the machine and thread changes
  const STITCHES_PER_MINUTE = 600;
  // ponytail: flat threshold, not density-based; past this a home design gets stiff and slow to sew
  const MANY_STITCHES = 15000;

  // ponytail: starting points from common machine-embroidery advice, not measured on each fabric.
  // No pull compensation: on detailed traced pictures it slows Ink/Stitch from seconds to minutes (koala: 12s -> 140s).
  const FABRICS = {
    cotton: { label: "Cotton", tip: "Woven cotton or linen. Hoop it with a tear-away stabiliser.", settings: { row_spacing_mm: 0.25, max_stitch_length_mm: 3, underlay: true, pull_compensation_mm: 0 } },
    knit: { label: "T-shirt", tip: "Stretchy knits. Use a cut-away stabiliser so the design doesn’t pucker. Stitches are a little lighter.", settings: { row_spacing_mm: 0.3, max_stitch_length_mm: 3, underlay: true, pull_compensation_mm: 0 } },
    denim: { label: "Denim", tip: "Denim, canvas and other sturdy fabric. A light tear-away stabiliser is enough.", settings: { row_spacing_mm: 0.25, max_stitch_length_mm: 3.5, underlay: true, pull_compensation_mm: 0 } },
    towel: { label: "Towel", tip: "Towels and fleece. Lay water-soluble topping on top so stitches don’t sink into the pile.", settings: { row_spacing_mm: 0.22, max_stitch_length_mm: 3, underlay: true, pull_compensation_mm: 0 } },
  };
  type Fabric = keyof typeof FABRICS;
  const FILLS: Array<[FillMethod, string]> = [["auto_fill", "Rows"], ["contour_fill", "Follow shape"], ["meander_fill", "Squiggle"], ["circular_fill", "Spiral"]];
  const DETAIL = ["Most detail", "Balanced", "Smoother", "Smoothest"];
  const TABS = [
    { key: "picture", label: "Picture", icon: ImageIcon },
    { key: "colours", label: "Colours", icon: Palette },
    { key: "stitches", label: "Stitches", icon: Spool },
    { key: "sew", label: "Sew", icon: ListOrdered },
  ] as const;
  type Tab = (typeof TABS)[number]["key"];

  let machines = $state<Record<string, Machine> | null>(null);
  let catalog = $state<Thread[]>([]);
  let loadError = $state(false);
  let machineKey = $state("brother_4x4");
  let name = $state("");
  let tab = $state<Tab>("picture");

  let picture = $state<Picture | null>(null);
  let cropping = $state(false);
  let removingBackground = $state(false);

  let numColors = $state(5);
  let smoothing = $state(1);
  let brand = $state("");
  /** The picture in thread colours, made from the settings in `key`. */
  let colours = $state<{ key: string; base: ImageData; swatches: Swatch[]; widthMm: number } | null>(null);
  let editing = $state<number | null>(null);

  let fabric = $state<Fabric | "custom">("cotton");
  let settings = $state<StitchSettings>({
    fill_method: "auto_fill", angle: 0, ...FABRICS.cotton.settings, min_detail_mm: 1, outline_thread: null, outline_style: "running",
  });
  let pickingOutline = $state(false);
  /** The last stitches made, from the colours and settings in `key`. */
  let result = $state<{ key: string; design: Design; rowSpacingMm: number } | null>(null);

  let busy = $state<"" | "colours" | "stitches">("");
  let error = $state("");
  let request = 0;
  let fileInput: HTMLInputElement;
  let colourCanvas = $state<HTMLCanvasElement>();

  onMount(() => {
    getMachines().then((m) => (machines = m)).catch(() => (loadError = true));
    getThreads().then((t) => (catalog = t)).catch(() => (loadError = true));
  });

  let machine = $derived(machines?.[machineKey]);
  let hoop = $derived({ w: machine?.max_w ?? 100, h: machine?.max_h ?? 100 });
  let brandName = $derived(machine?.name.split(" ")[0] ?? "");

  // Each step remembers the inputs it was made from, so changing anything earlier marks it out of date
  let colourKey = $derived(picture ? JSON.stringify([picture.image.src, picture.crop, picture.mmPerPx, picture.cx, picture.cy, picture.rotation, picture.flipX, picture.flipY, picture.adjust, hoop, numColors, smoothing, brand]) : "");
  let coloursFresh = $derived(!!colours && colours.key === colourKey);
  let stitchKey = $derived(colours ? JSON.stringify([colours.key, colours.swatches.map((s) => [s.sources, s.thread.id, s.stitched]), settings, machineKey]) : "");
  let stitchesFresh = $derived(coloursFresh && !!result && result.key === stitchKey);
  let design = $derived(result?.design);
  let stitchCount = $derived(design?.preview.reduce((sum, block) => sum + block.stitches.filter(([, , cmd]) => cmd === 0).length, 0) ?? 0);
  let fileName = $derived(`${name.trim() || "design"}.${design?.format ?? machine?.format ?? "pes"}`);
  let pictureSize = $derived(picture ? size(picture) : null);
  let lowResolution = $derived(!!picture && pxPerMm(picture) < MIN_PX_PER_MM);
  let painted = $derived(colours ? paint(colours.base, colours.swatches) : null);

  $effect(() => {
    if (!colourCanvas || !painted) return;
    colourCanvas.width = painted.width;
    colourCanvas.height = painted.height;
    colourCanvas.getContext("2d")!.putImageData(painted, 0, 0);
  });

  // Colours are quick: remake them whenever they're out of date and on screen
  $effect(() => {
    if (tab !== "colours" || !picture || coloursFresh) return;
    colourKey; // re-run (and restart the wait) on every change
    const timer = setTimeout(() => untrack(makeColoursNow), 400);
    return () => clearTimeout(timer);
  });
  // Stitches are slow: made on arrival at the tab, then only when asked
  $effect(() => {
    if ((tab === "stitches" || tab === "sew") && untrack(() => picture && !stitchesFresh && !busy)) untrack(makeStitchesNow);
  });

  function choose(file: File | undefined) {
    if (!file || !TYPES.includes(file.type)) {
      error = "Please choose a picture file (PNG, JPG or WebP).";
      return;
    }
    name = file.name.replace(/\.[^.]+$/, "") || "design";
    decode(file)
      .then((image) => {
        if (picture) {
          URL.revokeObjectURL(picture.original.src);
          if (picture.image !== picture.original) URL.revokeObjectURL(picture.image.src);
        }
        picture = load(image, hoop);
        colours = null;
        result = null;
        error = "";
        tab = "picture";
      })
      .catch(() => (error = "We couldn’t open this picture. Please try a different one."));
  }

  function changeMachine() {
    if (picture && !fits(picture, hoop)) fit(picture, hoop);
  }

  async function toggleBackground() {
    if (!picture) return;
    const p = picture;
    if (p.image !== p.original) {
      URL.revokeObjectURL(p.image.src);
      replaceImage(p, p.original);
      return;
    }
    removingBackground = true;
    error = "";
    try {
      replaceImage(p, await decode(await removeBackground(await toBlob(p.original))));
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      removingBackground = false;
    }
  }

  async function makeColoursNow() {
    if (!picture || busy) return;
    const id = ++request;
    const key = colourKey;
    busy = "colours";
    error = "";
    try {
      const exported = await exportPicture(picture, hoop);
      if (!exported) throw new Error("The picture is outside the hoop. Move it back in on the Picture tab.");
      if (exported.widthMm < 10) throw new Error("The picture is too small to stitch. Make it at least 10 mm wide.");
      const made = await makeColours(exported.file, { numColors, smoothing, brand });
      const loaded = await loadColours(made.image, made.colours);
      if (id !== request) return;
      colours = { key, ...loaded, widthMm: exported.widthMm };
      editing = null;
    } catch (err) {
      if (id === request) error = err instanceof Error ? err.message : String(err);
    } finally {
      if (id === request) busy = "";
    }
  }

  async function makeStitchesNow() {
    if (!coloursFresh) await makeColoursNow();
    if (!colours || !coloursFresh || busy) return;
    const stitched = colours.swatches.filter((s) => s.stitched);
    if (!stitched.length) {
      error = "Every colour is hidden. Show at least one on the Colours tab.";
      return;
    }
    const id = ++request;
    const key = stitchKey;
    busy = "stitches";
    error = "";
    try {
      const file = await toPng(paint(colours.base, colours.swatches));
      const made = await makeStitches(file, {
        threads: [...new Set(stitched.map((s) => s.thread.id))], widthMm: colours.widthMm, machineKey, settings: $state.snapshot(settings),
      });
      if (id !== request) return;
      result = { key, design: made, rowSpacingMm: settings.row_spacing_mm };
    } catch (err) {
      if (id === request) error = err instanceof Error ? err.message : String(err);
    } finally {
      if (id === request) busy = "";
    }
  }

  function setFabric(f: Fabric) {
    fabric = f;
    Object.assign(settings, FABRICS[f].settings);
  }

  function moveSwatch(i: number, by: number) {
    if (!colours) return;
    const list = colours.swatches;
    [list[i], list[i + by]] = [list[i + by], list[i]];
    editing = null;
  }

  function merge(from: number, into: number) {
    if (!colours) return;
    const list = colours.swatches;
    list[into].sources.push(...list[from].sources);
    list.splice(from, 1);
    editing = null;
  }

  function save() {
    if (design && stitchesFresh) saveFile(design.file_base64, fileName);
    else tab = "stitches";
  }
</script>

{#snippet slider(id: string, label: string, value: number, min: number, max: number, step: number, unit: string, set: (v: number) => void)}
  <div class="space-y-2">
    <div class="flex items-baseline justify-between gap-2">
      <Label id="{id}-label" class="font-semibold">{label}</Label>
      <span class="text-sm tabular-nums text-muted-foreground">{value}{unit}</span>
    </div>
    <Slider type="single" {value} onValueChange={set} {min} {max} {step} aria-labelledby="{id}-label" />
  </div>
{/snippet}

{#snippet heading(title: string, hint?: string)}
  <div>
    <h2 class="display text-4xl">{title}</h2>
    {#if hint}<p class="mt-2 text-muted-foreground">{hint}</p>{/if}
  </div>
{/snippet}

{#snippet stat(label: string, value: string)}
  <div class="flex items-baseline gap-1.5"><dt class="text-muted-foreground">{label}</dt><dd class="font-semibold tabular-nums">{value}</dd></div>
{/snippet}

<input bind:this={fileInput} id="picture-input" type="file" accept={TYPES.join(",")} class="sr-only"
  onchange={(e) => { choose(e.currentTarget.files?.[0]); e.currentTarget.value = ""; }} />

<div class="grid min-h-dvh grid-rows-[auto_1fr_auto] lg:h-dvh lg:grid-rows-[auto_minmax(0,1fr)_auto] print:block print:h-auto">
  <!-- Toolbar -->
  <header class="flex flex-wrap items-center gap-2 px-3 py-3 sm:gap-3 sm:px-5 print:hidden">
    <a href="/" class="display mr-2 text-3xl text-vermilion-500" aria-label="Stitchery home">Stitchery</a>
    <!-- Names the saved file: the extension shows next to it so that's clear -->
    <label class="hidden h-10 max-w-64 items-center gap-2 rounded-full bg-secondary px-4 focus-within:ring-3 focus-within:ring-ring/50 md:flex" title="The name of the file you save">
      <Pencil aria-hidden="true" class="size-4 shrink-0 text-muted-foreground" />
      <input bind:value={name} placeholder="Name your design" aria-label="File name" class="min-w-[3ch] flex-1 bg-transparent outline-none placeholder:text-muted-foreground [field-sizing:content]" />
      <span class="-ml-2 text-muted-foreground">.{fileName.split(".").pop()}</span>
    </label>
    <div class="ml-auto flex items-center gap-2">
      <NativeSelect.Root bind:value={machineKey} onchange={changeMachine} disabled={!machines} aria-label="Machine and hoop" class="max-w-[52vw] [&>select]:h-10 [&>select]:border-transparent [&>select]:bg-secondary [&>select]:pl-4">
        {#each Object.entries(machines ?? {}) as [key, m] (key)}
          <NativeSelect.Option value={key}>{m.name} · {m.max_w}×{m.max_h} mm</NativeSelect.Option>
        {/each}
      </NativeSelect.Root>
      <Button onclick={save} disabled={!picture || busy !== ""} class="h-10 gap-3 pr-1 pl-5">
        {stitchesFresh ? "Save file" : "Make file"}
        <span class="flex size-8 items-center justify-center rounded-full bg-vermilion-500 text-black"><ArrowUpRight aria-hidden="true" class="size-4" /></span>
      </Button>
    </div>
  </header>

  <div class="grid min-h-0 grid-cols-1 grid-rows-[60svh_auto_auto] gap-3 px-3 pb-3 sm:px-5 lg:grid-cols-[5.5rem_minmax(0,1fr)_24rem] lg:grid-rows-1 print:block">
    <!-- Rail -->
    <nav aria-label="Steps" class="order-2 flex gap-1 overflow-x-auto rounded-full bg-card p-1 lg:order-none lg:flex-col lg:rounded-[2rem] lg:p-1.5 print:hidden">
      {#each TABS as t, i (t.key)}
        <button type="button" aria-current={tab === t.key ? "step" : undefined} onclick={() => { tab = t.key; cropping = false; }}
          disabled={i > 0 && !picture}
          class="flex flex-1 items-center justify-center gap-1.5 rounded-full px-2 py-2 font-medium transition-colors hover:bg-muted disabled:opacity-40 aria-[current]:bg-ink-950 aria-[current]:text-white text-sm sm:text-base lg:flex-none lg:flex-col lg:gap-1 lg:rounded-3xl lg:py-3 lg:text-sm">
          <t.icon aria-hidden="true" class="size-5" />{t.label}
        </button>
      {/each}
    </nav>

    <!-- Canvas -->
    <main class="relative order-1 min-h-0 overflow-hidden rounded-[2rem] bg-card lg:order-none print:rounded-none">
      {#if tab === "picture"}
        <PictureEditor bind:picture bind:cropping {hoop} onpick={choose} />
      {:else}
        <div class="flex size-full items-center justify-center p-6 sm:p-10">
          {#if tab === "colours" && painted}
            <canvas bind:this={colourCanvas} class="checker max-h-full max-w-full rounded-lg shadow-sm transition-opacity {coloursFresh ? '' : 'opacity-30'}" aria-label="Your picture in thread colours. See-through parts aren’t stitched."></canvas>
          {:else if (tab === "stitches" || tab === "sew") && result}
            <div class="size-full transition-opacity {stitchesFresh ? '' : 'opacity-30'}">
              <StitchPreview preview={result.design.preview} bounds={result.design.bounds} rowSpacingMm={result.rowSpacingMm} />
            </div>
          {/if}
        </div>
        {#if busy || (tab === "stitches" && result && !stitchesFresh)}
          <div class="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6 text-center print:hidden">
            {#if busy}
              <span aria-hidden="true" class="size-10 animate-spin rounded-full border-4 border-vermilion-100 border-t-vermilion-500"></span>
              <p class="display text-3xl">{busy === "colours" ? "Matching threads…" : "Stitching…"}</p>
              {#if busy === "stitches"}<p class="text-muted-foreground">{settings.pull_compensation_mm > 0 ? "Closing gaps between colours can take a few minutes." : "This usually takes 5 to 30 seconds."}</p>{/if}
            {:else}
              <p class="display text-3xl">Settings changed</p>
              <Button onclick={makeStitchesNow}><RefreshCw aria-hidden="true" /> Update stitches</Button>
            {/if}
          </div>
        {/if}
      {/if}
      {#if error || loadError}
        <div role="alert" class="absolute inset-x-4 bottom-4 rounded-2xl bg-ink-950 px-4 py-3 text-white print:hidden">
          {loadError ? "We couldn’t load the machine and thread lists. Please refresh the page." : error}
        </div>
      {/if}
    </main>

    <!-- Settings panel -->
    <aside class="order-3 lg:min-h-0 lg:overflow-y-auto rounded-[2rem] bg-card p-5 lg:order-none print:overflow-visible print:p-0" aria-label="Settings">
      {#if tab === "picture"}
        <div class="space-y-7">
          {@render heading("Picture", picture ? "Drag to move, use the corners to resize and the orange dot to turn it. Double-click to crop." : "Start with a picture. Clear drawings, logos and patterns work best.")}
          {#if !picture}
            <Button size="lg" class="w-full" onclick={() => fileInput.click()}><ImagePlus aria-hidden="true" /> Choose a picture</Button>
          {:else}
            {@const p = picture}
            <section class="space-y-3">
              <h3 class="font-semibold">Size</h3>
              <div class="flex items-center gap-2">
                <Input type="number" min="5" max={hoop.w} step="1" aria-label="Width in mm" class="w-28"
                  value={Math.round(pictureSize?.w ?? 0)}
                  onchange={(e) => { const w = Number(e.currentTarget.value); if (w >= 5) p.mmPerPx = w / (p.crop.r - p.crop.l); }} />
                <span class="text-muted-foreground">× {Math.round(pictureSize?.h ?? 0)} mm</span>
              </div>
              <div class="flex flex-wrap gap-2">
                <Button variant="outline" onclick={() => fit(p, hoop)}><Maximize aria-hidden="true" /> Fit hoop</Button>
                <Button variant="outline" onclick={() => { p.cx = hoop.w / 2; p.cy = hoop.h / 2; }}>Centre</Button>
              </div>
              {#if lowResolution}
                <p role="status" class="rounded-2xl bg-vermilion-50 p-3 text-vermilion-800">This picture is small for its size in the hoop, so fine detail will be lost. Make it smaller or use a bigger picture.</p>
              {/if}
            </section>

            <section class="space-y-3">
              <h3 class="font-semibold">Turn and flip</h3>
              {@render slider("rotation", "Angle", p.rotation, -180, 180, 1, "°", (v) => (p.rotation = v))}
              <div class="flex flex-wrap gap-2">
                <Button variant="outline" size="icon-lg" aria-label="Turn left" onclick={() => (p.rotation = ((p.rotation + 270 + 180) % 360) - 180)}><RotateCcw aria-hidden="true" /></Button>
                <Button variant="outline" size="icon-lg" aria-label="Turn right" onclick={() => (p.rotation = ((p.rotation + 90 + 180) % 360) - 180)}><RotateCw aria-hidden="true" /></Button>
                <Button variant="outline" size="icon-lg" aria-label="Flip left to right" aria-pressed={p.flipX} onclick={() => (p.flipX = !p.flipX)}><FlipHorizontal2 aria-hidden="true" /></Button>
                <Button variant="outline" size="icon-lg" aria-label="Flip upside down" aria-pressed={p.flipY} onclick={() => (p.flipY = !p.flipY)}><FlipVertical2 aria-hidden="true" /></Button>
              </div>
            </section>

            <section class="space-y-3">
              <h3 class="font-semibold">Crop</h3>
              <div class="flex flex-wrap gap-2">
                <Button variant={cropping ? "default" : "outline"} aria-pressed={cropping} onclick={() => (cropping = !cropping)}><Crop aria-hidden="true" /> {cropping ? "Done cropping" : "Crop"}</Button>
                <Button variant="outline" onclick={() => { const { w } = size(p); p.crop = { l: 0, t: 0, r: p.image.naturalWidth, b: p.image.naturalHeight }; p.mmPerPx = Math.min(p.mmPerPx, (w * 2) / p.image.naturalWidth); cropping = false; }}>Reset crop</Button>
              </div>
            </section>

            <section class="space-y-3">
              <h3 class="font-semibold">Background</h3>
              <p class="text-muted-foreground">For photos with a busy background. Keeps only the main subject.</p>
              <Button variant={p.image !== p.original ? "outline" : "accent"} class="w-full" disabled={removingBackground} onclick={toggleBackground}>
                {#if removingBackground}
                  <span aria-hidden="true" class="size-5 animate-spin rounded-full border-2 border-black/25 border-t-black"></span> Removing background…
                {:else if p.image !== p.original}
                  <Undo2 aria-hidden="true" /> Put background back
                {:else}
                  <WandSparkles aria-hidden="true" /> Remove background
                {/if}
              </Button>
            </section>

            <section class="space-y-4">
              <div class="flex items-center justify-between">
                <h3 class="font-semibold">Adjust</h3>
                <Button variant="ghost" size="sm" onclick={() => (p.adjust = { ...NO_ADJUST })}>Reset</Button>
              </div>
              {@render slider("brightness", "Brightness", p.adjust.brightness, 0, 200, 1, "%", (v) => (p.adjust.brightness = v))}
              {@render slider("contrast", "Contrast", p.adjust.contrast, 0, 200, 1, "%", (v) => (p.adjust.contrast = v))}
              {@render slider("saturation", "Colour strength", p.adjust.saturation, 0, 200, 1, "%", (v) => (p.adjust.saturation = v))}
              {@render slider("hue", "Hue", p.adjust.hue, -180, 180, 1, "°", (v) => (p.adjust.hue = v))}
            </section>

            <Button variant="outline" class="w-full" onclick={() => fileInput.click()}><ImagePlus aria-hidden="true" /> Use a different picture</Button>
            <Button variant="accent" class="w-full" onclick={() => (tab = "colours")}>Next: colours <ArrowUpRight aria-hidden="true" /></Button>
          {/if}
        </div>
      {:else if tab === "colours"}
        <div class="space-y-7">
          {@render heading("Colours", "Each colour is one thread. Fewer colours means fewer thread changes.")}
          {@render slider("colours", "Thread colours", numColors, 2, 12, 1, "", (v) => (numColors = v))}
          <div class="space-y-2">
            <Label id="detail-label" class="font-semibold">Detail</Label>
            <ToggleGroup.Root type="single" spacing={1} value={String(smoothing)} onValueChange={(v) => { if (v) smoothing = Number(v); }} aria-labelledby="detail-label" class="flex-wrap">
              {#each DETAIL as d, i (d)}<ToggleGroup.Item value={String(i)} class="h-9 px-3">{d}</ToggleGroup.Item>{/each}
            </ToggleGroup.Root>
          </div>
          <div class="space-y-2">
            <Label for="brand" class="font-semibold">Thread brand</Label>
            <NativeSelect.Root id="brand" bind:value={brand} class="w-full">
              <NativeSelect.Option value="">Any brand (closest colours)</NativeSelect.Option>
              <NativeSelect.Option value="brother">Brother</NativeSelect.Option>
              <NativeSelect.Option value="janome">Janome</NativeSelect.Option>
              <NativeSelect.Option value="husqvarna">Husqvarna</NativeSelect.Option>
            </NativeSelect.Root>
          </div>

          {#if colours}
            <section class="space-y-2">
              <h3 class="font-semibold">Threads, in sewing order</h3>
              <p class="text-muted-foreground">Hidden colours aren’t stitched, so the fabric shows through. Changing the settings above starts the list again.</p>
              <ol class="space-y-2">
                {#each colours.swatches as s, i (s.sources[0])}
                  <li class="rounded-2xl border p-2 {s.stitched ? '' : 'opacity-60'}">
                    <div class="flex items-center gap-2">
                      <button type="button" class="size-9 shrink-0 rounded-full border border-black/15 shadow-inner" style="background:{s.thread.hex}"
                        aria-label="Change thread {s.thread.name}" aria-expanded={editing === i} onclick={() => (editing = editing === i ? null : i)}></button>
                      <div class="min-w-0 flex-1 leading-tight">
                        <div class="truncate font-semibold {s.stitched ? '' : 'line-through'}">{s.thread.name}</div>
                        <div class="text-sm text-muted-foreground">{s.thread.brand} {s.thread.code}</div>
                      </div>
                      <Button variant="ghost" size="icon-sm" aria-label={s.stitched ? `Don’t stitch ${s.thread.name}` : `Stitch ${s.thread.name}`} onclick={() => (s.stitched = !s.stitched)}>
                        {#if s.stitched}<Eye aria-hidden="true" />{:else}<EyeOff aria-hidden="true" />{/if}
                      </Button>
                      <Button variant="ghost" size="icon-sm" aria-label="Sew earlier" disabled={i === 0} onclick={() => moveSwatch(i, -1)}><ArrowUp aria-hidden="true" /></Button>
                      <Button variant="ghost" size="icon-sm" aria-label="Sew later" disabled={i === colours.swatches.length - 1} onclick={() => moveSwatch(i, 1)}><ArrowDown aria-hidden="true" /></Button>
                    </div>
                    {#if editing === i}
                      <div class="mt-2 space-y-2">
                        <ThreadPicker threads={catalog} value={s.thread.id} onpick={(t) => (s.thread = t)} />
                        {#if colours.swatches.length > 1}
                          <NativeSelect.Root aria-label="Merge into another colour" value="" class="h-10 w-full" onchange={(e) => merge(i, Number(e.currentTarget.value))}>
                            <NativeSelect.Option value="" disabled>Merge into another colour…</NativeSelect.Option>
                            {#each colours.swatches as other, j (other.sources[0])}
                              {#if j !== i}<NativeSelect.Option value={String(j)}>{other.thread.name}</NativeSelect.Option>{/if}
                            {/each}
                          </NativeSelect.Root>
                        {/if}
                      </div>
                    {/if}
                  </li>
                {/each}
              </ol>
            </section>
            <Button variant="accent" class="w-full" onclick={() => (tab = "stitches")}>Next: stitches <ArrowUpRight aria-hidden="true" /></Button>
          {/if}
        </div>
      {:else if tab === "stitches"}
        <div class="space-y-7">
          {@render heading("Stitches", "Tell us the fabric and we’ll set the stitches to suit it.")}
          <div class="space-y-2">
            <Label id="fabric-label" class="font-semibold">Fabric</Label>
            <ToggleGroup.Root type="single" spacing={1} value={fabric} onValueChange={(v) => { if (v && v in FABRICS) setFabric(v as Fabric); }} aria-labelledby="fabric-label" class="flex-wrap">
              {#each Object.entries(FABRICS) as [key, f] (key)}<ToggleGroup.Item value={key} class="h-9 px-3">{f.label}</ToggleGroup.Item>{/each}
            </ToggleGroup.Root>
            <p class="text-muted-foreground">{fabric === "custom" ? "Your own settings, below." : FABRICS[fabric].tip}</p>
          </div>

          <div class="space-y-2">
            <Label id="fill-label" class="font-semibold">Fill style</Label>
            <ToggleGroup.Root type="single" spacing={1} value={settings.fill_method} onValueChange={(v) => { if (v) settings.fill_method = v as FillMethod; }} aria-labelledby="fill-label" class="flex-wrap">
              {#each FILLS as [value, label] (value)}<ToggleGroup.Item {value} class="h-9 px-3">{label}</ToggleGroup.Item>{/each}
            </ToggleGroup.Root>
          </div>
          {#if settings.fill_method === "auto_fill"}
            {@render slider("angle", "Row angle", settings.angle, 0, 179, 1, "°", (v) => (settings.angle = v))}
          {/if}

          <section class="space-y-3">
            <h3 class="font-semibold">Outline</h3>
            <div class="flex items-center gap-2">
              <button type="button" class="checker size-9 shrink-0 rounded-full border border-black/15" style={settings.outline_thread ? `background:${catalog.find((t) => t.id === settings.outline_thread)?.hex}` : ""}
                aria-label="Choose outline thread" aria-expanded={pickingOutline} onclick={() => (pickingOutline = !pickingOutline)}></button>
              <span class="flex-1">{settings.outline_thread ? catalog.find((t) => t.id === settings.outline_thread)?.name : "No outline"}</span>
              {#if settings.outline_thread}<Button variant="ghost" size="sm" onclick={() => (settings.outline_thread = null)}>Remove</Button>{/if}
            </div>
            {#if pickingOutline}<ThreadPicker threads={catalog} value={settings.outline_thread ?? undefined} onpick={(t) => { settings.outline_thread = t.id; pickingOutline = false; }} />{/if}
            {#if settings.outline_thread}
              <ToggleGroup.Root type="single" spacing={1} value={settings.outline_style} onValueChange={(v) => { if (v === "running" || v === "bean") settings.outline_style = v; }} aria-label="Outline weight">
                <ToggleGroup.Item value="running" class="h-9 px-3">Thin</ToggleGroup.Item>
                <ToggleGroup.Item value="bean" class="h-9 px-3">Bold</ToggleGroup.Item>
              </ToggleGroup.Root>
            {/if}
          </section>

          <details class="group space-y-4 rounded-2xl bg-paper-100 p-4 [&[open]>summary]:mb-4">
            <summary class="cursor-pointer font-semibold">More settings</summary>
            <div class="space-y-5">
              {@render slider("spacing", "Gap between rows", settings.row_spacing_mm, 0.15, 0.8, 0.01, " mm", (v) => { settings.row_spacing_mm = v; fabric = "custom"; })}
              {@render slider("length", "Longest stitch", settings.max_stitch_length_mm, 1.5, 7, 0.1, " mm", (v) => { settings.max_stitch_length_mm = v; fabric = "custom"; })}
              {@render slider("pull", "Close gaps between colours", settings.pull_compensation_mm, 0, 1, 0.05, " mm", (v) => { settings.pull_compensation_mm = v; fabric = "custom"; })}
              <p class="-mt-3 text-sm text-muted-foreground">Stitches pull the fabric in, which can leave thin gaps between colours, most on stretchy fabric. This makes each shape a little bigger to cover them. Detailed pictures can take a few minutes.</p>
              {@render slider("detail", "Smallest detail", settings.min_detail_mm, 0.3, 3, 0.1, " mm", (v) => (settings.min_detail_mm = v))}
              <div class="flex items-start gap-3">
                <Checkbox id="underlay" checked={settings.underlay} onCheckedChange={(v) => { settings.underlay = v; fabric = "custom"; }} class="mt-0.5" />
                <div>
                  <Label for="underlay" class="font-semibold">Underlay</Label>
                  <p class="text-sm text-muted-foreground">A light first layer that holds the fabric flat. Leave on unless the design is tiny.</p>
                </div>
              </div>
            </div>
          </details>

          <Button class="w-full" disabled={busy !== "" || stitchesFresh} onclick={makeStitchesNow}><RefreshCw aria-hidden="true" /> {stitchesFresh ? "Stitches are up to date" : "Update stitches"}</Button>
          {#if stitchesFresh}<Button variant="accent" class="w-full" onclick={() => (tab = "sew")}>Next: sew it <ArrowUpRight aria-hidden="true" /></Button>{/if}
        </div>
      {:else if design}
        <div class="space-y-7">
          {@render heading("Sew it")}
          <ol class="divide-y rounded-2xl border">
            {#each design.preview as block, i (i)}
              <li class="flex items-center gap-3 px-3 py-2.5">
                <span class="w-5 font-semibold text-muted-foreground">{i + 1}</span>
                <span class="size-7 shrink-0 rounded-full border border-black/15 shadow-inner" style="background: {block.thread.hex}" aria-hidden="true"></span>
                <span class="leading-tight"><span class="font-semibold">{block.thread.name}</span><br /><span class="text-sm text-muted-foreground">{block.thread.brand} {block.thread.code}</span></span>
              </li>
            {/each}
          </ol>
          <ol class="list-decimal space-y-2 pl-5 leading-7 text-muted-foreground">
            <li>Save the file, then find <strong class="text-foreground">{fileName}</strong> in your Downloads folder and copy it onto a USB stick.</li>
            <li>Plug the USB stick into your {brandName} machine and choose the design on its screen.</li>
            <li>Sew each colour in the order shown. The machine stops when it’s time to change thread.</li>
          </ol>
          <div class="flex flex-wrap gap-2 print:hidden">
            <Button disabled={!stitchesFresh} onclick={save}>Save file for my {brandName} machine</Button>
            <Button variant="outline" onclick={() => window.print()}><Printer aria-hidden="true" /> Print</Button>
          </div>
        </div>
      {:else}
        {@render heading("Sew it", "Your thread list appears here once the stitches are made.")}
      {/if}
    </aside>
  </div>

  <!-- Status bar -->
  <footer class="flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-paper-200 px-5 py-2 text-sm print:border-0">
    {#if design && stitchesFresh}
      {@const w = design.bounds.widthUnits / 10}
      {@const h = design.bounds.heightUnits / 10}
      <dl class="contents">
        {@render stat("Size", `${w.toFixed(0)} × ${h.toFixed(0)} mm (${inches(w)} × ${inches(h)} in)`)}
        {@render stat("Stitches", stitchCount.toLocaleString())}
        {@render stat("Colours", String(design.preview.length))}
        {@render stat("Sewing time", `about ${Math.max(1, Math.round(stitchCount / STITCHES_PER_MINUTE))} min`)}
      </dl>
      {#if stitchCount > MANY_STITCHES}<span class="font-medium text-vermilion-700">That’s a lot of stitches: it may come out stiff. Try fewer colours, a smaller size or a wider row gap.</span>{/if}
    {:else if picture && pictureSize}
      <dl class="contents">{@render stat("Picture", `${Math.round(pictureSize.w)} × ${Math.round(pictureSize.h)} mm`)}{@render stat("Angle", `${picture.rotation}°`)}</dl>
    {:else}
      <span class="text-muted-foreground">Choose a picture to begin.</span>
    {/if}
  </footer>
</div>
