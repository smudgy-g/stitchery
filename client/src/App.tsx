import { useEffect, useState } from "react";
import { ArrowRight, Check, ChevronDown, CircleHelp, Layers3, Scissors, SlidersHorizontal, Sparkles } from "lucide-react";
import FileUploader from "./components/FileUploader";
import StitchPreview from "./components/StitchPreview";
import DownloadButton from "./components/DownloadButton";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { useFileUpload } from "./hooks/useFileUpload";

// Production builds set VITE_API_URL=/api (same origin, proxied by Caddy).
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

type Machine = { name: string; max_w: number; max_h: number; format: string; threads: string };

// Below this the image has less detail than a stitch can show, so fills come out blocky
const MIN_PX_PER_MM = 4;

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [fileWidthPx, setFileWidthPx] = useState(0);
  const [numColors, setNumColors] = useState(5);
  const [machines, setMachines] = useState<Record<string, Machine> | null>(null);
  const [machinesError, setMachinesError] = useState(false);
  const [selectedMachine, setSelectedMachine] = useState("brother_4x4");
  const [targetWidthMm, setTargetWidthMm] = useState(80);
  const [removeBackground, setRemoveBackground] = useState(false);
  const { preview, bounds, isLoading, uploadFile, error, resetFileUpload, base64File, format } =
    useFileUpload(`${API_URL}/upload`);

  useEffect(() => {
    fetch(`${API_URL}/machines`)
      .then((response) => response.json())
      .then(setMachines)
      .catch(() => setMachinesError(true));
  }, []);
  const machine = machines?.[selectedMachine];

  const handleFileChange = (nextFile: File | null, widthPx = 0) => {
    setFile(nextFile);
    setFileWidthPx(widthPx);
    resetFileUpload();
  };

  const widthValid = !!machine && Number.isFinite(targetWidthMm) && targetWidthMm >= 10 && targetWidthMm <= machine.max_w;
  const lowResolution = !!file && widthValid && fileWidthPx / targetWidthMm < MIN_PX_PER_MM;
  const stitchCount = preview?.reduce((sum, block) => sum + block.stitches.filter(([, , cmd]) => cmd === 0).length, 0);

  const handleGenerate = () => {
    if (!file || !widthValid || isLoading) return;
    resetFileUpload();
    void uploadFile(file, { numColors, targetWidthMm, machineKey: selectedMachine, removeBackground });
  };

  return (
    <div className="min-h-screen bg-white text-gray-950">
      <header className="border-b border-gray-200">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between border-x border-gray-200 px-5 py-4 sm:px-10">
          <a href="#top" className="flex items-center gap-2.5 text-base font-semibold tracking-tight" aria-label="Stitchery home">
            <span className="flex size-8 items-center justify-center rounded-lg bg-sky-500 text-white"><Scissors aria-hidden="true" className="size-4" /></span>
            stitchery<span className="text-sky-500">.</span>
          </a>
          <div className="flex items-center gap-3 text-xs sm:gap-6">
            <a href="#studio" className="font-medium text-gray-600 hover:text-gray-950">The studio</a>
            <span className="hidden h-4 w-px bg-gray-200 sm:block" />
            <span className="hidden items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-gray-500 sm:flex"><span className="size-1.5 rounded-full bg-sky-500" /> Image to embroidery</span>
          </div>
        </div>
      </header>

      <main id="top" className="page-grid mx-auto max-w-[1200px] border-x border-gray-200">
        <div className="px-5 sm:px-10">
          <section className="border-b border-gray-200 pb-10 pt-14 sm:pb-14 sm:pt-20">
            <div className="mb-6 flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.16em] text-sky-600">
              <span className="h-px w-7 bg-sky-500" /> The digital embroidery studio / 001
            </div>
            <h1 className="max-w-4xl text-[clamp(3rem,7vw,5.6rem)] font-medium leading-[1.02] tracking-[-0.065em] text-gray-950">
              Your image, <br /><span className="text-gray-400">made of stitches.</span>
            </h1>
            <div className="mt-7 flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
              <p className="max-w-xl text-base leading-7 text-gray-600 sm:text-lg">
                Turn simple artwork into a machine-ready embroidery file. Crop, choose your threads, and see the stitches before you sew.
              </p>
              <a href="#studio" className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-sky-600 hover:text-sky-700">
                Start creating <ArrowRight aria-hidden="true" className="size-4" />
              </a>
            </div>
          </section>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-gray-200 py-5 font-mono text-[11px] uppercase tracking-wider text-gray-500 sm:gap-x-10">
            <span className="flex items-center gap-2"><span className="text-sky-600">01</span> Add your artwork</span>
            <ArrowRight aria-hidden="true" className="hidden size-3 text-gray-300 sm:block" />
            <span className="flex items-center gap-2"><span className="text-sky-600">02</span> Set the details</span>
            <ArrowRight aria-hidden="true" className="hidden size-3 text-gray-300 sm:block" />
            <span className="flex items-center gap-2"><span className="text-sky-600">03</span> Preview & download</span>
          </div>

          <section id="studio" aria-labelledby="studio-heading" className="pb-16 pt-10 sm:pb-24 sm:pt-14">
            <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.16em] text-sky-600">Workspace / new design</p>
                <h2 id="studio-heading" className="text-3xl font-medium tracking-[-0.045em] sm:text-4xl">Make something worth keeping.</h2>
              </div>
              <span className="rounded-full border border-gray-200 bg-white px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-gray-500">{machine ? `${machine.format} · ${machine.name}` : "Loading machines…"}</span>
            </div>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)] lg:items-start">
              <div className="space-y-5">
                <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-[0_6px_24px_-16px_rgba(15,23,42,0.2)]">
                  <div className="flex items-center gap-3 border-b border-gray-100 px-5 py-4">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-sky-50 text-sky-600"><Scissors aria-hidden="true" className="size-4" /></span>
                    <div><h3 className="text-sm font-semibold">01 / Your artwork</h3><p className="text-xs text-gray-500">A clear logo, drawing, or pattern works best.</p></div>
                  </div>
                  <div className="p-5"><FileUploader onFileSelect={handleFileChange} confirmed={!!file} aspect={machine ? machine.max_w / machine.max_h : 1} /></div>
                </div>

                <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-[0_6px_24px_-16px_rgba(15,23,42,0.2)]">
                  <div className="flex items-center gap-3 border-b border-gray-100 px-5 py-4">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-gray-100 text-gray-700"><SlidersHorizontal aria-hidden="true" className="size-4" /></span>
                    <div><h3 className="text-sm font-semibold">02 / Design settings</h3><p className="text-xs text-gray-500">Fit your hoop and choose the thread count.</p></div>
                  </div>
                  <div className="space-y-5 p-5">
                    <div>
                      <label htmlFor="hoopSelect" className="mb-2 block text-xs font-semibold text-gray-700">Machine &amp; hoop</label>
                      <div className="relative">
                        <select id="hoopSelect" value={selectedMachine} disabled={!machines} onChange={(e) => {
                          const key = e.target.value;
                          setSelectedMachine(key);
                          handleFileChange(null); // the confirmed crop was shaped for the old hoop
                          setTargetWidthMm((width) => Math.min(width, machines?.[key].max_w ?? width));
                          resetFileUpload();
                        }} className="h-10 w-full appearance-none rounded-lg border border-gray-200 bg-white px-3 pr-9 text-sm text-gray-950 outline-none focus-visible:border-sky-500 focus-visible:ring-2 focus-visible:ring-sky-500/20">
                          {Object.entries(machines ?? {}).map(([key, m]) => <option key={key} value={key}>{m.name} — {m.max_w} × {m.max_h} mm · {m.format.toUpperCase()}</option>)}
                        </select>
                        <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-3 size-4 text-gray-500" />
                      </div>
                      {machinesError && <p role="alert" className="mt-2 text-xs text-red-600">Couldn’t load machines. Is the server running?</p>}
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label htmlFor="targetWidth" className="mb-2 block text-xs font-semibold text-gray-700">Width <span className="font-normal text-gray-400">/ mm</span></label>
                        <Input type="number" id="targetWidth" value={targetWidthMm} min={10} max={machine?.max_w} onChange={(e) => { setTargetWidthMm(Number(e.target.value)); resetFileUpload(); }} aria-invalid={!widthValid} />
                      </div>
                      <div>
                        <label htmlFor="numColorSelect" className="mb-2 block text-xs font-semibold text-gray-700">Thread colours</label>
                        <div className="relative">
                          <select id="numColorSelect" value={numColors} onChange={(e) => { setNumColors(Number(e.target.value)); resetFileUpload(); }} className="h-10 w-full appearance-none rounded-lg border border-gray-200 bg-white px-3 pr-9 text-sm text-gray-950 outline-none focus-visible:border-sky-500 focus-visible:ring-2 focus-visible:ring-sky-500/20">
                            {Array.from({ length: 11 }, (_, i) => i + 2).map((num) => <option key={num} value={num}>{num} colours</option>)}
                          </select>
                          <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-3 size-4 text-gray-500" />
                        </div>
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-xs font-semibold text-gray-700">
                      <input type="checkbox" checked={removeBackground} onChange={(e) => { setRemoveBackground(e.target.checked); resetFileUpload(); }} className="size-4 accent-sky-500" />
                      Remove background <span className="font-normal text-gray-400">/ for busy backgrounds; keeps only the main subject</span>
                    </label>
                    <p className="flex items-start gap-2 text-xs leading-5 text-gray-500"><CircleHelp aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" /> Height follows your hoop’s shape{machine && widthValid ? `: ${targetWidthMm} × ${Math.floor(targetWidthMm * machine.max_h / machine.max_w)} mm` : ""}.</p>
                    {lowResolution && <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">This image is low resolution for {targetWidthMm} mm, so fine detail will be lost. Use a larger image, a smaller width, or a looser crop.</p>}
                    {machine && !widthValid && <p role="alert" className="text-xs text-red-600">Choose a width between 10 and {machine.max_w} mm.</p>}
                    <Button size="lg" className="w-full" disabled={!file || !widthValid || isLoading} onClick={handleGenerate}>
                      {isLoading ? <><span aria-hidden="true" className="size-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> Generating stitches…</> : <><Sparkles aria-hidden="true" /> Generate stitches <ArrowRight aria-hidden="true" /></>}
                    </Button>
                    {!file && <p className="text-center text-xs text-gray-400">Select and confirm your artwork to get started.</p>}
                    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
                  </div>
                </div>
              </div>

              <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-[0_6px_24px_-16px_rgba(15,23,42,0.2)]">
                <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-gray-100 text-gray-700"><Layers3 aria-hidden="true" className="size-4" /></span>
                    <div><h3 className="text-sm font-semibold">03 / Stitch preview</h3><p className="text-xs text-gray-500">A look at the actual stitches in your file.</p></div>
                  </div>
                  <span className="hidden items-center gap-1.5 rounded-full border border-gray-200 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-gray-500 sm:flex"><span className={`size-1.5 rounded-full ${preview ? "bg-sky-500" : "bg-gray-300"}`} />{preview ? "Ready" : "Waiting"}</span>
                </div>
                <div className="hatched p-3 sm:p-5">
                  <div className="preview-grid flex aspect-square items-center justify-center overflow-hidden rounded-xl border border-gray-200 bg-white p-5 sm:p-8">
                    {preview && bounds ? <StitchPreview preview={preview} bounds={bounds} /> : (
                      <div className="flex max-w-xs flex-col items-center text-center">
                        <div className="mb-5 flex size-20 items-center justify-center rounded-2xl border border-gray-200 bg-white shadow-sm"><Layers3 aria-hidden="true" className="size-8 text-sky-500" strokeWidth={1.5} /></div>
                        <p className="text-lg font-medium tracking-tight text-gray-950">Your stitches go here</p>
                        <p className="mt-2 text-sm leading-6 text-gray-500">Upload an image, adjust your settings, and generate a design to see the stitch-by-stitch result.</p>
                      </div>
                    )}
                  </div>
                </div>
                <div className="border-t border-gray-100 px-5 py-5">
                  {preview && bounds ? (
                    <div className="mb-5 flex flex-wrap gap-x-7 gap-y-3 text-sm">
                      <div><p className="font-mono text-[10px] uppercase tracking-wider text-gray-400">Design size</p><p className="mt-1 font-semibold">{(bounds.widthUnits / 10).toFixed(1)} × {(bounds.heightUnits / 10).toFixed(1)} mm</p></div>
                      <div><p className="font-mono text-[10px] uppercase tracking-wider text-gray-400">Stitches</p><p className="mt-1 font-semibold">{stitchCount?.toLocaleString()}</p></div>
                      <div><p className="font-mono text-[10px] uppercase tracking-wider text-gray-400">Colour blocks</p><p className="mt-1 font-semibold">{preview.length}</p></div>
                    </div>
                  ) : <p className="mb-4 flex items-center gap-2 text-xs text-gray-500"><Check aria-hidden="true" className="size-4 text-sky-500" /> The preview is drawn from the generated embroidery file.</p>}
                  <DownloadButton base64Content={base64File ?? ""} format={format ?? machine?.format ?? "pes"} disabled={!base64File} />
                </div>
              </div>
            </div>
          </section>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 px-5 py-5 text-xs text-gray-500 sm:px-10">
          <span>Stitchery / Made for the joy of making.</span>
          <span>Best with clean line art & simple patterns.</span>
        </div>
      </main>
    </div>
  );
}

export default App;
