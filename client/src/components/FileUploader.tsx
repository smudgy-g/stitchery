import { useEffect, useRef, useState } from "react";
import { Check, ImagePlus, Maximize2, RotateCw, Upload } from "lucide-react";
import ReactCrop, { centerCrop, convertToPixelCrop, makeAspectCrop, type Crop, type PixelCrop } from "react-image-crop";
import { Button } from "./ui/button";
import "react-image-crop/dist/ReactCrop.css";

interface Props {
  /** widthPx is the confirmed image's pixel width, for the resolution check. */
  onFileSelect: (file: File | null, widthPx?: number) => void;
  confirmed: boolean;
  /** Hoop width / height. The crop is locked to it, so every confirmed image fits the hoop. */
  aspect: number;
}

/** Largest centred crop of the hoop's shape. */
function hoopCrop(image: HTMLImageElement, aspect: number) {
  const crop = centerCrop(makeAspectCrop({ unit: "%", width: 100 }, aspect, image.width, image.height), image.width, image.height);
  return { crop, pixelCrop: convertToPixelCrop(crop, image.width, image.height) };
}

export default function FileUploader({ onFileSelect, confirmed, aspect }: Props) {
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [imgSrc, setImgSrc] = useState("");
  const [crop, setCrop] = useState<Crop>();
  const [completedCrop, setCompletedCrop] = useState<PixelCrop | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [cropError, setCropError] = useState("");
  const imgRef = useRef<HTMLImageElement | null>(null);
  const readerRef = useRef<FileReader | null>(null);
  const selectionId = useRef(0);

  const resetCrop = () => {
    if (!imgRef.current) return;
    const { crop: next, pixelCrop } = hoopCrop(imgRef.current, aspect);
    setCrop(next);
    setCompletedCrop(pixelCrop);
  };

  // Reshape the crop box when the hoop changes (the parent drops the old confirmed image)
  useEffect(() => {
    const image = imgRef.current;
    if (!image?.complete || !image.width) return;
    selectionId.current++;
    const { crop: next, pixelCrop } = hoopCrop(image, aspect);
    setCrop(next);
    setCompletedCrop(pixelCrop);
  }, [aspect]);

  const emit = (canvas: HTMLCanvasElement, name: string) => {
    const id = selectionId.current;
    canvas.toBlob((blob) => {
      if (id !== selectionId.current) return;
      if (blob) onFileSelect(new File([blob], name, { type: "image/png" }), canvas.width);
      else setCropError("Could not prepare this image. Try another file.");
    }, "image/png");
  };

  const chooseFile = (nextFile: File) => {
    selectionId.current++;
    readerRef.current?.abort();
    onFileSelect(null);
    setSourceFile(nextFile);
    setImgSrc("");
    setCrop(undefined);
    setCompletedCrop(null);
    setCropError("");
    const reader = new FileReader();
    readerRef.current = reader;
    reader.onload = () => setImgSrc(reader.result as string);
    reader.readAsDataURL(nextFile);
  };

  // Rotate the source 90° clockwise so cropping and "use full image" both see the rotated artwork.
  const rotate = () => {
    const image = imgRef.current;
    if (!image || !sourceFile) return;
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalHeight;
    canvas.height = image.naturalWidth;
    const ctx = canvas.getContext("2d");
    if (!ctx) { setCropError("Could not rotate this image. Try another file."); return; }
    ctx.translate(canvas.width, 0);
    ctx.rotate(Math.PI / 2);
    ctx.drawImage(image, 0, 0);

    const id = ++selectionId.current;
    onFileSelect(null);
    canvas.toBlob((blob) => {
      if (id !== selectionId.current) return;
      if (blob) chooseFile(new File([blob], sourceFile.name, { type: "image/png" }));
      else setCropError("Could not rotate this image. Try another file.");
    }, "image/png");
  };

  const applyCrop = () => {
    const image = imgRef.current;
    if (!image || !completedCrop || !completedCrop.width || !completedCrop.height) return;

    const canvas = document.createElement("canvas");
    const scaleX = image.naturalWidth / image.width;
    const scaleY = image.naturalHeight / image.height;
    canvas.width = Math.round(completedCrop.width * scaleX);
    // Floor, so pixel rounding can never make the design taller than the hoop
    canvas.height = Math.floor(canvas.width / aspect);
    const ctx = canvas.getContext("2d");
    if (!ctx) { setCropError("Could not crop this image. Try another file."); return; }

    ctx.drawImage(image, completedCrop.x * scaleX, completedCrop.y * scaleY,
      completedCrop.width * scaleX, completedCrop.height * scaleY,
      0, 0, canvas.width, canvas.height);
    emit(canvas, "cropped_design.png");
  };

  // Pads the whole image out to the hoop's shape instead of cutting anything off.
  const fitWholeImage = () => {
    const image = imgRef.current;
    if (!image) return;
    selectionId.current++;
    resetCrop();

    const w = image.naturalWidth, h = image.naturalHeight;
    const canvas = document.createElement("canvas");
    canvas.width = w / h > aspect ? w : Math.ceil(h * aspect);
    canvas.height = w / h > aspect ? Math.floor(w / aspect) : h;
    const ctx = canvas.getContext("2d");
    if (!ctx) { setCropError("Could not prepare this image. Try another file."); return; }

    // ponytail: pads with the top-left pixel's colour, so a plain background is stripped with the padding.
    // A busy or gradient background shows a visible border; crop instead for those.
    ctx.drawImage(image, 0, 0);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    ctx.fillStyle = a < 128 ? "#ffffff" : `rgb(${r} ${g} ${b})`;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, Math.floor((canvas.width - w) / 2), Math.floor((canvas.height - h) / 2));
    emit(canvas, "fitted_design.png");
  };

  return (
    <div className="space-y-4">
      <input
        id="artwork-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="peer sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) chooseFile(file);
          event.target.value = "";
        }}
      />
      <label
        htmlFor="artwork-input"
        onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          const file = event.dataTransfer.files[0];
          if (file && ["image/png", "image/jpeg", "image/webp"].includes(file.type)) chooseFile(file);
          else setCropError("Choose a PNG, JPEG, or WebP image.");
        }}
        className={`flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-5 py-6 text-center transition-colors peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-sky-500 peer-focus-visible:ring-offset-2 ${isDragging ? "border-sky-500 bg-sky-50" : "border-gray-300 bg-gray-50/60 hover:border-sky-400 hover:bg-sky-50/40"}`}
      >
        <span className="mb-3 flex size-10 items-center justify-center rounded-lg border border-gray-200 bg-white text-sky-600 shadow-sm"><Upload aria-hidden="true" className="size-4" /></span>
        <span className="text-sm font-semibold text-gray-900">Drop an image or <span className="text-sky-600 underline decoration-sky-300 underline-offset-4">browse files</span></span>
        <span className="mt-1.5 text-xs text-gray-500">PNG, JPG, or WebP · simple artwork looks best</span>
      </label>

      {sourceFile && imgSrc && (
        <div className="rounded-xl border border-gray-200 bg-white p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-gray-700"><ImagePlus aria-hidden="true" className="size-4 shrink-0 text-sky-600" /><span className="truncate">{sourceFile.name}</span></div>
            {confirmed && <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-sky-700"><Check aria-hidden="true" className="size-3.5" /> Ready</span>}
          </div>
          <div className="preview-grid flex justify-center overflow-hidden rounded-lg border border-gray-100 p-2">
            <ReactCrop
              crop={crop}
              aspect={aspect}
              onChange={(next) => { selectionId.current++; setCrop(next); if (confirmed) onFileSelect(null); }}
              onComplete={setCompletedCrop}
            >
              <img
                ref={imgRef}
                src={imgSrc}
                alt="Your artwork. Drag the crop handles to select an area."
                onLoad={resetCrop}
                className="max-h-80 max-w-full"
              />
            </ReactCrop>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-gray-500">Crop is shaped like your hoop. Drag to choose an area, or fit the whole image.</p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={rotate} aria-label="Rotate image 90 degrees clockwise"><RotateCw aria-hidden="true" /> Rotate</Button>
              <Button type="button" variant="ghost" size="sm" onClick={fitWholeImage}><Maximize2 aria-hidden="true" /> Fit whole image</Button>
              <Button type="button" variant="secondary" size="sm" onClick={applyCrop} disabled={!completedCrop?.width || !completedCrop.height}>Confirm crop</Button>
            </div>
          </div>
        </div>
      )}
      {cropError && <p role="alert" className="text-xs text-red-600">{cropError}</p>}
    </div>
  );
}
