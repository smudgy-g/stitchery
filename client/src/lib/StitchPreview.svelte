<script lang="ts">
  import type { Block, Bounds } from "./api";

  /** `pxPerMm` is the on-screen size: the canvas is the design's real size at that scale. */
  let { preview, bounds, pxPerMm, rowSpacingMm = 0.25 }: { preview: Block[]; bounds: Bounds; pxPerMm: number; rowSpacingMm?: number } = $props();
  let canvas: HTMLCanvasElement;
  // Stitch units are 0.1 mm
  let cssW = $derived((bounds.widthUnits / 10) * pxPerMm), cssH = $derived((bounds.heightUnits / 10) * pxPerMm);

  $effect(() => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // ponytail: capped at 8000px a side; past that browsers refuse the canvas, so deep zoom on a big hoop softens
    const dpr = Math.min(window.devicePixelRatio || 1, 8000 / Math.max(cssW, cssH, 1));
    canvas.width = Math.max(1, Math.ceil(cssW * dpr));
    canvas.height = Math.max(1, Math.ceil(cssH * dpr));
    const { minX, minY } = bounds;
    const scale = (pxPerMm * dpr) / 10;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // Thread-like width: matches the fill row spacing, so fills read solid
    // while outlines and stitch direction stay visible. Square ends; round ones smear outlines.
    ctx.lineWidth = Math.max(1, rowSpacingMm * 10 * scale);
    ctx.lineJoin = "round";
    for (const block of preview) {
      ctx.strokeStyle = block.thread.hex;
      ctx.beginPath();
      let pen = false;
      for (const [x, y, cmd] of block.stitches) {
        const px = (x - minX) * scale;
        const py = (y - minY) * scale;
        if (cmd !== 0 || !pen) {
          ctx.moveTo(px, py);
          pen = true;
        } else ctx.lineTo(px, py);
      }
      ctx.stroke();
    }
  });
</script>

<div role="img" aria-label="The stitches in your embroidery file">
  <canvas bind:this={canvas} class="block" style="width:{cssW}px;height:{cssH}px"></canvas>
</div>
