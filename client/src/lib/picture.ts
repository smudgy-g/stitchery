/** A picture placed in the hoop. Lengths are in mm from the hoop's top-left; crop is in source pixels. */
export type Picture = {
  image: HTMLImageElement;
  /** The picture as chosen, kept so a removed background can be put back. */
  original: HTMLImageElement;
  crop: { l: number; t: number; r: number; b: number };
  mmPerPx: number;
  cx: number;
  cy: number;
  rotation: number;
  flipX: boolean;
  flipY: boolean;
  adjust: Adjust;
};
/** Percentages (100 = unchanged), hue in degrees. */
export type Adjust = { brightness: number; contrast: number; saturation: number; hue: number };
export type Hoop = { w: number; h: number };

export const NO_ADJUST: Adjust = { brightness: 100, contrast: 100, saturation: 100, hue: 0 };
// Pixels per mm the server works at, and its largest working size
const PX_PER_MM = 10;
const MAX_PX = 800;
// Kept clear at the hoop edge: pull compensation widens fills, and the frame itself can't be sewn right up to
const HOOP_MARGIN_MM = 1.5;

export const filterCss = (a: Adjust) =>
  `brightness(${a.brightness}%) contrast(${a.contrast}%) saturate(${a.saturation}%) hue-rotate(${a.hue}deg)`;

/** Visible (cropped) size in mm, before rotation. */
export const size = (p: Picture) => ({ w: (p.crop.r - p.crop.l) * p.mmPerPx, h: (p.crop.b - p.crop.t) * p.mmPerPx });

function bounds(p: Picture) {
  const { w, h } = size(p);
  const a = (p.rotation * Math.PI) / 180;
  const bw = Math.abs(w * Math.cos(a)) + Math.abs(h * Math.sin(a));
  const bh = Math.abs(w * Math.sin(a)) + Math.abs(h * Math.cos(a));
  return { x: p.cx - bw / 2, y: p.cy - bh / 2, w: bw, h: bh };
}

export function load(image: HTMLImageElement, hoop: Hoop): Picture {
  const p: Picture = {
    image, original: image, crop: { l: 0, t: 0, r: image.naturalWidth, b: image.naturalHeight },
    mmPerPx: 1, cx: 0, cy: 0, rotation: 0, flipX: false, flipY: false, adjust: { ...NO_ADJUST },
  };
  fit(p, hoop);
  return p;
}

/** Scales the picture to fill most of the hoop, centred. */
export function fit(p: Picture, hoop: Hoop) {
  const b = bounds(p);
  p.mmPerPx *= Math.min((hoop.w * 0.9) / b.w, (hoop.h * 0.9) / b.h); // inside the edge margin for any hoop over 30 mm
  p.cx = hoop.w / 2;
  p.cy = hoop.h / 2;
}

export function fits(p: Picture, hoop: Hoop) {
  const b = bounds(p);
  const m = HOOP_MARGIN_MM - 0.01;
  return b.x >= m && b.y >= m && b.x + b.w <= hoop.w - m && b.y + b.h <= hoop.h - m;
}

/** Swaps in a different image of the same picture (e.g. with its background removed), keeping crop and size. */
export function replaceImage(p: Picture, image: HTMLImageElement) {
  const f = image.naturalWidth / p.image.naturalWidth;
  p.crop = { l: p.crop.l * f, t: p.crop.t * f, r: p.crop.r * f, b: p.crop.b * f };
  p.mmPerPx /= f;
  p.image = image;
}

/** Source pixels per mm of what is stitched; low means fine detail is lost. */
export const pxPerMm = (p: Picture) => 1 / p.mmPerPx;

/**
 * The part of the hoop the picture covers, as a PNG with everything else transparent,
 * and its width in mm. Null when the picture is outside the hoop.
 */
export async function exportPicture(p: Picture, hoop: Hoop): Promise<{ file: File; widthMm: number } | null> {
  const b = bounds(p);
  const m = HOOP_MARGIN_MM;
  const x = Math.max(m, b.x), y = Math.max(m, b.y);
  const w = Math.min(hoop.w - m, b.x + b.w) - x, h = Math.min(hoop.h - m, b.y + b.h) - y;
  if (w <= 0 || h <= 0) return null;
  const s = Math.min(PX_PER_MM, MAX_PX / Math.max(w, h));
  const canvas = document.createElement("canvas");
  // Ceil the width and floor the height: the server derives height from the pixel shape, which must stay in the hoop
  canvas.width = Math.ceil(w * s);
  canvas.height = Math.max(1, Math.floor(h * s));
  const ctx = canvas.getContext("2d")!;
  ctx.imageSmoothingQuality = "high";
  ctx.setTransform(s, 0, 0, s, -x * s, -y * s);
  ctx.translate(p.cx, p.cy);
  ctx.rotate((p.rotation * Math.PI) / 180);
  ctx.scale(p.flipX ? -1 : 1, p.flipY ? -1 : 1);
  ctx.filter = filterCss(p.adjust);
  const { w: vw, h: vh } = size(p);
  const { l, t, r, b: bottom } = p.crop;
  ctx.drawImage(p.image, l, t, r - l, bottom - t, -vw / 2, -vh / 2, vw, vh);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  return blob && { file: new File([blob], "picture.png", { type: "image/png" }), widthMm: Math.min(canvas.width / s, hoop.w - 2 * m) };
}

export async function decode(blob: Blob): Promise<HTMLImageElement> {
  const image = new Image();
  image.src = URL.createObjectURL(blob);
  await image.decode();
  return image;
}

/** The image as a PNG, for sending to the server. */
export function toBlob(image: HTMLImageElement): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  canvas.getContext("2d")!.drawImage(image, 0, 0);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Couldn’t read the picture."))), "image/png"));
}
