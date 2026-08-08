interface Props {
  previewUrl?: string;
  onFileSelect: (file: File) => void;
}

function FileUploader({ previewUrl, onFileSelect }: Props) {
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      onFileSelect(selectedFile);
    }
  };
  return (
    <div>
      <input
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"
        onChange={handleFileChange}
      />
      <div>
        {previewUrl && (
          <div>
            <img src={previewUrl} alt="Preview" style={{ maxWidth: "300px" }} />
          </div>
        )}
      </div>
    </div>
  );
}

export default FileUploader;
