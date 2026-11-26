<script lang="ts">
  import { Upload } from "@lucide/svelte";
  import { buttonVariants } from "$lib/components/ui/button";
  import { filterCss, size, type Hoop, type Picture } from "./picture";

  interface Props {
    picture: Picture | null;
    hoop: Hoop;
    /** Crop mode: edge handles trim the picture instead of corner/rotate handles. */
    cropping: boolean;
    onpick: (file: File | undefined) => void;
  }
  let { picture = $bindable(), hoop, cropping = $bindable(), onpick }: Props = $props();

  const MIN_MM = 5;
  let width = $state(0), height = $state(0);
  let hoopEl = $state<HTMLDivElement>();
  let dragging = $state(false);
  /** Screen pixels per mm */
  let k = $derived(Math.max(0.1, Math.min((width - 48) / hoop.w, (height - 48) / hoop.h)));

  let frame = $derived.by(() => {
    if (!picture) return "";
    const { w, h } = size(picture);
    return `left:${picture.cx * k}px;top:${picture.cy * k}px;width:${w * k}px;height:${h * k}px;transform:translate(-50%,-50%) rotate(${picture.rotation}deg)`;
  });
  // The whole image, placed so its crop window lines up with the frame
  let imageStyle = $derived.by(() => {
    if (!picture) return "";
    const m = picture.mmPerPx * k;
    return `left:${-picture.crop.l * m}px;top:${-picture.crop.t * m}px;width:${picture.image.naturalWidth * m}px;height:${picture.image.naturalHeight * m}px;filter:${filterCss(picture.adjust)}`;
  });
  let flip = $derived(picture ? `transform:scale(${picture.flipX ? -1 : 1},${picture.flipY ? -1 : 1})` : "");

  type Kind = "move" | "rotate" | "scale" | "l" | "r" | "t" | "b";
  const EDGES: Array<[Kind, string]> = [
    ["l", "top-1/2 left-0 h-8 w-2 cursor-ew-resize"],
    ["r", "top-1/2 left-full h-8 w-2 cursor-ew-resize"],
    ["t", "top-0 left-1/2 h-2 w-8 cursor-ns-resize"],
    ["b", "top-full left-1/2 h-2 w-8 cursor-ns-resize"],
  ];

  function toMm(e: PointerEvent) {
    const rect = hoopEl!.getBoundingClientRect();
    return { x: (e.clientX - rect.left) / k, y: (e.clientY - rect.top) / k };
  }

  function drag(e: PointerEvent, kind: Kind) {
    const p = picture;
    if (!p || e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);
    const start = { ...p, crop: { ...p.crop } };
    const p0 = toMm(e);
    dragging = true;

    const move = (ev: PointerEvent) => {
      const pt = toMm(ev);
      const dx = pt.x - p0.x, dy = pt.y - p0.y;
      if (kind === "move") {
        p.cx = start.cx + dx;
        p.cy = start.cy + dy;
      } else if (kind === "rotate") {
        let angle = (Math.atan2(pt.y - start.cy, pt.x - start.cx) * 180) / Math.PI + 90;
        const step = ev.shiftKey ? 15 : 90;
        const snapped = Math.round(angle / step) * step;
        if (ev.shiftKey || Math.abs(angle - snapped) < 4) angle = snapped;
        p.rotation = Math.round((((angle + 180) % 360) + 360) % 360 - 180);
      } else if (kind === "scale") {
        const ratio = Math.hypot(pt.x - start.cx, pt.y - start.cy) / Math.max(0.01, Math.hypot(p0.x - start.cx, p0.y - start.cy));
        const { w, h } = size(start);
        p.mmPerPx = start.mmPerPx * Math.max(ratio, MIN_MM / Math.min(w, h));
      } else {
        // Crop: move one edge along the frame's own axis, keeping the opposite edge still
        const a = (start.rotation * Math.PI) / 180;
        const horizontal = kind === "l" || kind === "r";
        const [ax, ay] = horizontal ? [Math.cos(a), Math.sin(a)] : [-Math.sin(a), Math.cos(a)];
        const dir = kind === "r" || kind === "b" ? 1 : -1;
        const grow = (dx * ax + dy * ay) * dir; // mm outward
        const flipped = horizontal ? start.flipX : start.flipY;
        // Which source edge sits on this side, after flipping
        const far = (dir === 1) !== flipped;
        const [lo, hi, max] = horizontal ? ["l", "r", p.image.naturalWidth] as const : ["t", "b", p.image.naturalHeight] as const;
        const min = MIN_MM / start.mmPerPx;
        let applied: number;
        if (far) {
          p.crop[hi] = Math.min(max, Math.max(start.crop[lo] + min, start.crop[hi] + grow / start.mmPerPx));
          applied = (p.crop[hi] - start.crop[hi]) * start.mmPerPx;
        } else {
          p.crop[lo] = Math.max(0, Math.min(start.crop[hi] - min, start.crop[lo] - grow / start.mmPerPx));
          applied = (start.crop[lo] - p.crop[lo]) * start.mmPerPx;
        }
        p.cx = start.cx + (applied / 2) * dir * ax;
        p.cy = start.cy + (applied / 2) * dir * ay;
      }
    };
    const end = () => {
      dragging = false;
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", end);
      el.removeEventListener("pointercancel", end);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
  }

  function nudge(e: KeyboardEvent) {
    if (!picture) return;
    const step = e.shiftKey ? 10 : 1;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (e.key === "Escape") cropping = false;
    if (!moves[e.key]) return;
    e.preventDefault();
    picture.cx += moves[e.key][0];
    picture.cy += moves[e.key][1];
  }

  let isDropping = $state(false);
</script>

<div
  bind:clientWidth={width}
  bind:clientHeight={height}
  role="presentation"
  class="relative size-full overflow-hidden select-none"
  ondragover={(e) => { e.preventDefault(); isDropping = true; }}
  ondragleave={() => (isDropping = false)}
  ondrop={(e) => { e.preventDefault(); isDropping = false; onpick(e.dataTransfer?.files[0]); }}
  onpointerdown={() => (cropping = false)}
>
  <div bind:this={hoopEl} class="preview-grid absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-[2rem]" style="width:{hoop.w * k}px;height:{hoop.h * k}px">
    {#if picture}
      <!-- The picture. In crop mode the trimmed-off parts show faintly around it. -->
      <div class="absolute" style={frame}>
        <div class="absolute inset-0" style={flip}>
          {#if cropping}<img src={picture.image.src} alt="" class="absolute max-w-none opacity-30" style={imageStyle} draggable="false" />{/if}
          <div class="absolute inset-0 overflow-hidden">
            <img src={picture.image.src} alt="What will be stitched" class="absolute max-w-none" style={imageStyle} draggable="false" />
          </div>
        </div>
      </div>
    {/if}

    <!-- Hoop edge: outside it nothing is stitched, so it is faded out -->
    <div class="pointer-events-none absolute inset-0 rounded-[2rem] border-[3px] border-dashed border-vermilion-500 shadow-[0_0_0_100vmax_rgb(245_238_232/0.8)]"></div>
    <span class="pointer-events-none absolute -top-7 left-1/2 -translate-x-1/2 text-sm font-medium whitespace-nowrap text-muted-foreground">Hoop · {hoop.w} × {hoop.h} mm</span>

    {#if picture}
      <!-- Handles sit above the fade so they work outside the hoop too -->
      <div
        class="absolute cursor-move touch-none outline-2 outline-offset-0 outline-ink-950 focus-visible:outline-vermilion-500 {dragging ? '' : 'transition-[outline-color]'}"
        style={frame}
        role="slider"
        aria-label="Picture position. Use the arrow keys to move it."
        aria-valuenow={Math.round(picture.cx)}
        tabindex="0"
        onpointerdown={(e) => drag(e, "move")}
        ondblclick={() => (cropping = !cropping)}
        onkeydown={nudge}
      >
        {#if cropping}
          {#each EDGES as [edge, cls] (edge)}
            <span class="absolute -translate-1/2 touch-none rounded-full bg-ink-950 ring-2 ring-white {cls}" onpointerdown={(e) => drag(e, edge)} aria-hidden="true"></span>
          {/each}
        {:else}
          {#each ["top-0 left-0 cursor-nwse-resize", "top-0 left-full cursor-nesw-resize", "top-full left-0 cursor-nesw-resize", "top-full left-full cursor-nwse-resize"] as cls (cls)}
            <span class="absolute size-4 -translate-1/2 touch-none rounded-full border-2 border-ink-950 bg-white {cls}" onpointerdown={(e) => drag(e, "scale")} aria-hidden="true"></span>
          {/each}
          <span class="absolute bottom-full left-1/2 h-6 w-0.5 -translate-x-1/2 bg-ink-950" aria-hidden="true"></span>
          <span class="absolute bottom-full left-1/2 mb-6 size-5 -translate-x-1/2 cursor-grab touch-none rounded-full bg-vermilion-500 ring-2 ring-ink-950" onpointerdown={(e) => drag(e, "rotate")} aria-hidden="true"></span>
        {/if}
      </div>
    {:else}
      <label
        for="picture-input"
        class="absolute inset-0 flex cursor-pointer flex-col items-center justify-center gap-4 rounded-[2rem] p-6 text-center transition-colors {isDropping ? 'bg-vermilion-100/70' : 'hover:bg-vermilion-50/60'}"
      >
        <span class={buttonVariants({ size: "lg" })}><Upload aria-hidden="true" /> Choose a picture</span>
        <span class="max-w-64 text-muted-foreground">or drag one here. Simple drawings and logos work best.</span>
      </label>
    {/if}
  </div>
</div>
