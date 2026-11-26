// Production builds set VITE_API_URL=/api (same origin, proxied by Caddy).
export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export type Machine = { name: string; max_w: number; max_h: number; format: string };
export type Thread = { id: string; brand: string; code: string; name: string; hex: string; rgb: [number, number, number] };
export type Colour = { thread: Thread; stitched: boolean };
export type Block = { color: string; stitches: Array<[number, number, number]>; thread: Thread };
export type Bounds = { widthUnits: number; heightUnits: number; minX: number; minY: number; maxX: number; maxY: number };
export type Design = { file_base64: string; format: string; preview: Block[]; bounds: Bounds; threads: Thread[] };

export type FillMethod = "auto_fill" | "contour_fill" | "meander_fill" | "circular_fill";
export type StitchSettings = {
  fill_method: FillMethod;
  angle: number;
  row_spacing_mm: number;
  max_stitch_length_mm: number;
  underlay: boolean;
  pull_compensation_mm: number;
  min_detail_mm: number;
  outline_thread: string | null;
  outline_style: "running" | "bean";
};

type Params = Record<string, string | number | boolean | string[] | null>;

/** Calls the server. Throws an Error whose message is written for the person using the app. */
async function call(path: string, params: Params = {}, file?: Blob): Promise<Response> {
  const url = new URL(`${API_URL}${path}`, window.location.href);
  for (const [key, value] of Object.entries(params)) {
    for (const v of Array.isArray(value) ? value : value === null ? [] : [value]) url.searchParams.append(key, String(v));
  }
  let init: RequestInit | undefined;
  if (file) {
    const body = new FormData();
    body.append("file", file, "picture.png");
    init = { method: "POST", body };
  }

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error("We couldn’t reach Stitchery. Please check your internet connection and try again.");
  }
  if (response.ok) return response;
  if (response.status === 400) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new Error(typeof detail === "string" ? detail : "Something about this picture didn’t work. Please try a different one.");
  }
  if (response.status === 504) throw new Error("This picture took too long to turn into stitches. Try turning “Close gaps between colours” down to 0, fewer thread colours, or a simpler picture.");
  throw new Error("Sorry, that didn’t work. Try fewer thread colours or a simpler picture. If it keeps happening, try again later.");
}

export const getMachines = (): Promise<Record<string, Machine>> => call("/machines").then((r) => r.json());
export const getThreads = (): Promise<Thread[]> => call("/threads").then((r) => r.json());
export const removeBackground = (picture: Blob): Promise<Blob> => call("/remove-background", {}, picture).then((r) => r.blob());

/** The picture reduced to thread colours (a PNG as base64), largest area first. */
export const makeColours = (
  picture: Blob,
  options: { numColors: number; smoothing: number; brand: string },
): Promise<{ image: string; colours: Colour[] }> =>
  call("/colours", { num_colors: options.numColors, smoothing: options.smoothing, brands: options.brand ? [options.brand] : [] }, picture).then((r) => r.json());

/** Stitches for a flat picture: each opaque colour is one of `threads` (in sewing order), transparent is fabric. */
export const makeStitches = (
  picture: Blob,
  options: { threads: string[]; widthMm: number; machineKey: string; settings: StitchSettings },
): Promise<Design> =>
  call("/stitch", { thread: options.threads, target_width_mm: options.widthMm, machine_key: options.machineKey, ...options.settings }, picture).then((r) => r.json());

export function saveFile(base64: string, fileName: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))]));
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(link.href);
}

export const inches = (mm: number) => (mm / 25.4).toFixed(1);
