// Same origin: the server serves this app in production, and Vite proxies /api to it in dev.
const API_URL = "/api";

export type Machine = { name: string; max_w: number; max_h: number; format: string };
export type Thread = { id: string; brand: string; code: string; name: string; hex: string; rgb: [number, number, number] };
export type Colour = { thread: Thread; stitched: boolean };
export type Block = { color: string; stitches: Array<[number, number, number]>; thread: Thread };
export type Bounds = { widthUnits: number; heightUnits: number; minX: number; minY: number; maxX: number; maxY: number };
export type Design = { file_base64: string; format: string; preview: Block[]; bounds: Bounds; threads: Thread[] };

/** A design saved to someone's account. */
export type SavedDesign = {
  id: string; name: string; machine_key: string; format: string; thumbnail: string; threads: Thread[];
  stitch_count: number; width_mm: number; height_mm: number; created_at: string;
};

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

/** Calls the server. Throws an Error whose message is written for the person using the app.
 * `request` sends JSON or another method, and `token` signs the call in as the current person. */
async function call(path: string, params: Params = {}, file?: Blob, request: { method?: string; json?: unknown; token?: string } = {}): Promise<Response> {
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
  if (request.json !== undefined || request.method || request.token) {
    init = {
      method: request.method ?? (request.json !== undefined ? "POST" : "GET"),
      body: request.json !== undefined ? JSON.stringify(request.json) : undefined,
      headers: {
        ...(request.json !== undefined && { "Content-Type": "application/json" }),
        ...(request.token && { Authorization: `Bearer ${request.token}` }),
      },
    };
  }

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error("We couldn’t reach Stitchery. Please check your internet connection and try again.");
  }
  if (response.ok) return response;
  if ([400, 401, 404, 413, 503].includes(response.status)) {
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

export const listDesigns = (token: string): Promise<SavedDesign[]> => call("/designs", {}, undefined, { token }).then((r) => r.json());
export const saveDesign = (token: string, design: { name: string; machine_key: string; file_base64: string; threads: string[] }) =>
  call("/designs", {}, undefined, { token, json: design });
export const getDesignFile = (token: string, id: string): Promise<{ file_base64: string; file_name: string }> =>
  call(`/designs/${encodeURIComponent(id)}/file`, {}, undefined, { token }).then((r) => r.json());
export const deleteDesign = (token: string, id: string) => call(`/designs/${encodeURIComponent(id)}`, {}, undefined, { token, method: "DELETE" });

export function saveFile(base64: string, fileName: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))]));
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(link.href);
}

export const inches = (mm: number) => (mm / 25.4).toFixed(1);
