import { useState, useEffect, useMemo } from "react";
import "./App.css";
import FileUploader from "./components/FileUploader";
import StitchPreview from "./components/StitchPreview";
import { useFileUpload } from "./hooks/useFileUpload";
import DownloadButton from "./components/DownloadButton";

const HOOP_PRESETS = {
  brother_4x4: { name: "Brother 4x4 (100 × 100 mm)", maxW: 100, maxH: 100 },
  brother_5x7: { name: "Brother 5x7 (130 × 180 mm)", maxW: 130, maxH: 180 },
  brother_8x12: { name: "Brother 8x12 (200 × 300 mm)", maxW: 200, maxH: 300 },
} as const;

type HoopKey = keyof typeof HOOP_PRESETS;

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [numColors, setNumColors] = useState<number>(5);
  const [selectedHoop, setSelectedHoop] = useState<HoopKey>("brother_4x4");
  const [targetWidthMm, setTargetWidthMm] = useState<number>(80);

  const {
    preview,
    bounds,
    isLoading,
    uploadFile,
    error,
    resetFileUpload,
    base64File,
  } = useFileUpload("http://127.0.0.1:8000/upload");

  const previewUrl = useMemo(() => {
    if (!file) return null;

    const objectUrl = URL.createObjectURL(file);
    return objectUrl;
  }, [file]);

  useEffect(() => {
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const handleFileChange = (file: File) => {
    setFile(file);
  };

  const handleUpload = () => {
    resetFileUpload();

    if (file) {
      uploadFile(file, {
        numColors,
        targetWidthMm,
        hoopKey: selectedHoop,
      });
    }
  };

  return (
    <>
      <section>
        <h1>Embroidery</h1>
        <aside>
          <label htmlFor="numColorSelect">
            Number of colours:
            <select
              name="numColors"
              id="numColorSelect"
              value={numColors}
              onChange={(e) => setNumColors(Number(e.target.value))}
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((num) => (
                <option key={`${num}-colors`} value={num}>
                  {num}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="hoopSelect">
            Hoop:
            <select
              name="hoopSelect"
              id="hoopSelect"
              value={selectedHoop}
              onChange={(e) => setSelectedHoop(e.target.value as HoopKey)}
            >
              {Object.entries(HOOP_PRESETS).map(([key, hoop]) => (
                <option key={key} value={key}>
                  {hoop.name}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="targetWidth">
            Target Width (mm):
            <input
              type="number"
              id="targetWidth"
              value={targetWidthMm}
              min={10}
              max={HOOP_PRESETS[selectedHoop].maxW}
              onChange={(e) => setTargetWidthMm(Number(e.target.value))}
            />
          </label>
        </aside>
        <FileUploader onFileSelect={handleFileChange} />

        {error && <p className="error">{error}</p>}

        <button onClick={handleUpload} disabled={!file || isLoading}>
          {isLoading ? "Uploading..." : "Upload"}
        </button>
        <DownloadButton base64Content={base64File} disabled={!preview} />

        <div>
          {preview && (
            <>
              <StitchPreview preview={preview} bounds={bounds} />
            </>
          )}
        </div>
      </section>
    </>
  );
}

export default App;
