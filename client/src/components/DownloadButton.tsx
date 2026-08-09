import { downloadBase64File } from "../helpers/downloadBase64File";

export default function DownloadButton({
  base64Content,
  disabled,
}: {
  base64Content: string;
  disabled: boolean;
}) {
  const handleDownload = () => {
    // Example for binary data like a .pes or image file
    downloadBase64File(base64Content, "design.pes", "application/octet-stream");
  };

  return (
    <button onClick={handleDownload} disabled={disabled}>
      Download PES File
    </button>
  );
}
