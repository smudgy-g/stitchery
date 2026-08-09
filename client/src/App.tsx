import { useState, useEffect, useMemo } from "react";
import "./App.css";
import FileUploader from "./components/FileUploader";
import StitchPreview from "./components/StitchPreview";
import { useFileUpload } from "./hooks/useFileUpload";
import DownloadButton from "./components/DownloadButton";

function App() {
  const [file, setFile] = useState<File | null>(null);

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
      uploadFile(file);
    }
  };

  return (
    <>
      <section>
        <h1>Embroidery</h1>
        <aside>
          <label htmlFor="numColors">
            Number of colours:
            <select name="numColors" id="numColors" defaultValue={5}>
              {Array.from({ length: 12 }, (_, i) => i + 1).map((num) => (
                <option key={`${num}-colors`} value={num}>
                  {num}
                </option>
              ))}
            </select>
          </label>
          <button onClick={handleUpload} disabled={!file || isLoading}>
            {isLoading ? "Uploading..." : "Upload"}
          </button>
          <DownloadButton base64Content={base64File} disabled={!preview} />
        </aside>
        <FileUploader onFileSelect={handleFileChange} previewUrl={previewUrl} />

        {error && <p className="error">{error}</p>}

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
