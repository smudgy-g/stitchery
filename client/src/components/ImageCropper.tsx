import { useState } from "react";
import ReactCrop, {
  type Crop,
  centerCrop,
  makeAspectCrop,
} from "react-image-crop";

const HOOP_PRESETS = {
  brother_4x4: { name: "Brother 4x4 (100 x 100 mm)", maxW: 100, maxH: 100 },
  brother_5x7: { name: "Brother 5x7 (130 x 180 mm)", maxW: 130, maxH: 180 },
  brother_8x12: { name: "Brother 8x12 (200 x 300 mm)", maxW: 200, maxH: 300 },
};

export function ImageCropper({ src }) {
  const [crop, setCrop] = useState<Crop>();
  return (
    <ReactCrop crop={crop} onChange={(c) => setCrop(c)}>
      <img src={src} />
    </ReactCrop>
  );
}
