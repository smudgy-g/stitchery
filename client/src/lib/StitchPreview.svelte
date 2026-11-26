<script lang="ts">
  import type { Block, Bounds } from "./api";

  let { preview, bounds, rowSpacingMm = 0.25 }: { preview: Block[]; bounds: Bounds; rowSpacingMm?: number } = $props();
  let canvas: HTMLCanvasElement;

  $effect(() => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { widthUnits, heightUnits, minX, minY } = bounds;
    const scale = Math.min(canvas.width / widthUnits, canvas.height / heightUnits);
    const offsetX = (canvas.width - widthUnits * scale) / 2;
    const offsetY = (canvas.height - heightUnits * scale) / 2;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // Thread-like width: matches the fill row spacing (units are 0.1 mm), so fills read solid
    // while outlines and stitch direction stay visible. Square ends; round ones smear outlines.
    ctx.lineWidth = Math.max(1, rowSpacingMm * 10 * scale);
    ctx.lineJoin = "round";
    for (const block of preview) {
      ctx.strokeStyle = block.thread.hex;
      ctx.beginPath();
      let pen = false;
      for (const [x, y, cmd] of block.stitches) {
        const px = offsetX + (x - minX) * scale;
        const py = offsetY + (y - minY) * scale;
        if (cmd !== 0 || !pen) {
          ctx.moveTo(px, py);
          pen = true;
        } else ctx.lineTo(px, py);
      }
      ctx.stroke();
    }
  });
</script>

<div role="img" aria-label="The stitches in your embroidery file" class="size-full">
  <canvas bind:this={canvas} width="1000" height="1000" class="block size-full object-contain"></canvas>
</div>
