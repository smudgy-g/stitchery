import { useRef, useState } from "react";
import { Check, ImagePlus, RotateCcw, Upload } from "lucide-react";
import ReactCrop, { type Crop, type PixelCrop } from "react-image-crop";
import { Button } from "./ui/button";
import "react-image-crop/dist/ReactCrop.css";

interface Props {
  onFileSelect: (file: File | null) => void;
  confirmed: boolean;
}

export default function FileUploader({ onFileSelect, confirmed }: Props) {
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [imgSrc, setImgSrc] = useState("");
  const [crop, setCrop] = useState<Crop>();
  const [completedCrop, setCompletedCrop] = useState<PixelCrop | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [cropError, setCropError] = useState("");
  const imgRef = useRef<HTMLImageElement | null>(null);
  const readerRef = useRef<FileReader | null>(null);
  const selectionId = useRef(0);

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

  const applyCrop = () => {
    const image = imgRef.current;
    if (!image || !completedCrop || !completedCrop.width || !completedCrop.height) return;

    const canvas = document.createElement("canvas");
    const scaleX = image.naturalWidth / image.width;
    const scaleY = image.naturalHeight / image.height;
    canvas.width = Math.round(completedCrop.width * scaleX);
    canvas.height = Math.round(completedCrop.height * scaleY);
    const ctx = canvas.getContext("2d");
    if (!ctx) { setCropError("Could not crop this image. Try another file."); return; }

    ctx.drawImage(image, completedCrop.x * scaleX, completedCrop.y * scaleY,
      completedCrop.width * scaleX, completedCrop.height * scaleY,
      0, 0, canvas.width, canvas.height);

    const id = selectionId.current;
    canvas.toBlob((blob) => {
      if (id !== selectionId.current) return;
      if (blob) onFileSelect(new File([blob], "cropped_design.png", { type: "image/png" }));
      else setCropError("Could not crop this image. Try another file.");
    }, "image/png");
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
              onChange={(next) => { selectionId.current++; setCrop(next); if (confirmed) onFileSelect(null); }}
              onComplete={setCompletedCrop}
            >
              <img
                ref={imgRef}
                src={imgSrc}
                alt="Your artwork. Drag the crop handles to select an area."
                onLoad={(event) => {
                  const { width, height } = event.currentTarget;
                  setCrop({ unit: "%", x: 0, y: 0, width: 100, height: 100 });
                  setCompletedCrop({ unit: "px", x: 0, y: 0, width, height });
                }}
                className="max-h-80 max-w-full"
              />
            </ReactCrop>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-gray-500">Drag to crop, or keep the full image.</p>
            <div className="flex gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => {
                selectionId.current++;
                if (imgRef.current) {
                  const { width, height } = imgRef.current;
                  setCrop({ unit: "%", x: 0, y: 0, width: 100, height: 100 });
                  setCompletedCrop({ unit: "px", x: 0, y: 0, width, height });
                }
                onFileSelect(sourceFile);
              }}><RotateCcw aria-hidden="true" /> Use full image</Button>
              <Button type="button" variant="secondary" size="sm" onClick={applyCrop} disabled={!completedCrop?.width || !completedCrop.height}>Confirm crop</Button>
            </div>
          </div>
        </div>
      )}
      {cropError && <p role="alert" className="text-xs text-red-600">{cropError}</p>}
    </div>
  );
}
