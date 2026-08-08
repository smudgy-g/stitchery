import { downloadBase64File } from "../helpers/downloadBase64File";

export default function DownloadButton({
  base64Content,
}: {
  base64Content: string;
}) {
  const handleDownload = () => {
    // Example for binary data like a .pes or image file
    downloadBase64File(base64Content, "design.pes", "application/octet-stream");
  };

  return <button onClick={handleDownload}>Download PES File</button>;
}
