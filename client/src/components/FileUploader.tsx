import { useState, useRef } from "react";
import ReactCrop, {
  type Crop,
  type PixelCrop,
  centerCrop,
  makeAspectCrop,
} from "react-image-crop";

import 'react-image-crop/dist/ReactCrop.css'

interface Props {
  onFileSelect: (file: File) => void;
}

export default function FileUploader({  onFileSelect }: Props) {
  const [imgSrc, setImgSrc] = useState<string>("");
  const [crop, setCrop] = useState<Crop>();
  const [completedCrop, setCompletedCrop] = useState<PixelCrop | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      const reader = new FileReader();
      reader.onload = () => {
        setImgSrc(reader.result as string);
      };
      reader.readAsDataURL(selectedFile);
    }
  };

  const onImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const { width, height } = e.currentTarget;
    const initialCrop = centerCrop(
      makeAspectCrop({ unit: "%", width: 90 }, 1, width, height),
      width,
      height,
    );
    setCrop(initialCrop);
  };

  const applyCrop = async () => {
    const image = imgRef.current;
    if (!image || !completedCrop) return;

    const canvas = document.createElement("canvas");
    const scaleX = image.naturalWidth / image.width;
    const scaleY = image.naturalHeight / image.height;

    canvas.width = completedCrop.width * scaleX;
    canvas.height = completedCrop.height * scaleY;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(
      image,
      completedCrop.x * scaleX,
      completedCrop.y * scaleY,
      completedCrop.width * scaleX,
      completedCrop.height * scaleY,
      0,
      0,
      canvas.width,
      canvas.height,
    );

    canvas.toBlob((blob) => {
      if (blob) {
        const croppedFile = new File([blob], "cropped_design.png", {
          type: "image/png",
        });
        onFileSelect(croppedFile);
      }
    }, "image/png");
  };

  return (
    <div>
      <input
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"
        onChange={handleFileChange}
      />
      {imgSrc && (
        <div style={{ marginTop: "1rem" }}>
          <ReactCrop
            crop={crop}
            onChange={(c) => setCrop(c)}
            onComplete={(c) => setCompletedCrop(c)}
          >
            <img
              ref={imgRef}
              src={imgSrc}
              alt="Crop target"
              onLoad={onImageLoad}
              style={{ maxWidth: "100%", maxHeight: "400px" }}
            />
          </ReactCrop>

          <button
            type="button"
            onClick={applyCrop}
            style={{ marginTop: "0.5rem", display: "block" }}
          >
            Confirm Crop Selection
          </button>
        </div>
      )}
      {/*<div>
        {previewUrl && (
          <div>
            <img src={previewUrl} alt="Preview" style={{ maxWidth: "300px" }} />
          </div>
        )}
      </div>*/}
    </div>
  );
}
