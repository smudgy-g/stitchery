import { Download } from "lucide-react";
import { downloadBase64File } from "../helpers/downloadBase64File";
import { Button } from "./ui/button";

export default function DownloadButton({ base64Content, format, disabled }: { base64Content: string; format: string; disabled: boolean }) {
  return (
    <Button
      variant={disabled ? "secondary" : "default"}
      className="w-full"
      disabled={disabled}
      onClick={() => downloadBase64File(base64Content, `design.${format}`, "application/octet-stream")}
    >
      <Download aria-hidden="true" /> Download {format.toUpperCase()} file
    </Button>
  );
}
