import type { Colour, Thread } from "./api";
import { decode } from "./picture";

/** One thread in the design. `sources` are the picture colours it covers (more than one after a merge). */
export type Swatch = { sources: number[]; thread: Thread; stitched: boolean };

const rgbKey = (r: number, g: number, b: number) => (r << 16) | (g << 8) | b;

export async function loadColours(base64: string, colours: Colour[]) {
  const image = await decode(await (await fetch(`data:image/png;base64,${base64}`)).blob());
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(image, 0, 0);
  URL.revokeObjectURL(image.src);
  const swatches: Swatch[] = colours.map((c) => ({ sources: [rgbKey(...c.thread.rgb)], thread: c.thread, stitched: c.stitched }));
  return { base: ctx.getImageData(0, 0, canvas.width, canvas.height), swatches };
}

/** The flat picture with each swatch's thread colour; colours not stitched become transparent. */
export function paint(base: ImageData, swatches: Swatch[]): ImageData {
  const map = new Map<number, [number, number, number, number]>();
  for (const s of swatches) for (const src of s.sources) map.set(src, s.stitched ? [...s.thread.rgb, 255] : [0, 0, 0, 0]);
  const out = new ImageData(base.width, base.height);
  const a = base.data, b = out.data;
  for (let i = 0; i < a.length; i += 4) {
    if (a[i + 3] < 128) continue;
    const c = map.get(rgbKey(a[i], a[i + 1], a[i + 2]));
    if (c) b.set(c, i);
  }
  return out;
}

export function toPng(image: ImageData): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  canvas.getContext("2d")!.putImageData(image, 0, 0);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Couldn’t prepare the picture."))), "image/png"));
}

/** Hue, then lightness: a readable order for a wall of thread swatches. Greys go last. */
export function threadOrder(t: Thread) {
  const [r, g, b] = t.rgb.map((v) => v / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  if (d < 0.08) return 1000 + max;
  const hue = max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return Math.round(hue * 4) * 10 + max;
}
