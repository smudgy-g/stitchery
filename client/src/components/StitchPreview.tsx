import { useEffect, useRef } from "react";

interface Props {
  svg?: any;
  preview: Array<{ color: string; stitches: Array<[number, number, number]> }>;
  bounds: {
    widthUnits: number;
    heightUnits: number;
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
  };
}

function StitchPreview({ svg, preview, bounds }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (preview) {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const { heightUnits, widthUnits, minX, maxX, minY, maxY } = bounds;
      const scale = Math.min(
        canvas.width / widthUnits,
        canvas.height / heightUnits,
      );

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.lineWidth = 1;
      ctx.lineJoin = "round";

      for (const block of preview) {
        ctx.strokeStyle = block.color;
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
    }
  }, [preview, bounds]);
  return (
    <>
      <canvas ref={canvasRef} width={600} height={600} />
    </>
  );
}
export default StitchPreview;
