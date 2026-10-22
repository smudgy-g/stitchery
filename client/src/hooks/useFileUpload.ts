import { useRef, useState } from "react";

interface UploadResponse {
  file_base64: string;
  format: string;
  preview: Array<{ color: string; stitches: Array<[number, number, number]> }>;
  bounds: {
    widthUnits: number;
    heightUnits: number;
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
  };
}

interface UseFileUploadReturn {
  isLoading: boolean;
  base64File: string | null;
  format: string | null;
  preview: Array<{
    color: string;
    stitches: Array<[number, number, number]>;
  }> | null;
  error: string | null;
  bounds: UploadResponse["bounds"] | null;
  uploadFile: (
    file: File,
    options: {
      numColors: number;
      targetWidthMm: number;
      machineKey: string;
      removeBackground: boolean;
    },
  ) => Promise<void>;
  resetFileUpload: () => void;
}

export function useFileUpload(uploadUrl: string): UseFileUploadReturn {
  const requestId = useRef(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [base64File, setBase64File] = useState<string | null>(null);
  const [format, setFormat] = useState<string | null>(null);
  const [preview, setPreview] = useState<UploadResponse["preview"] | null>(null);
  const [bounds, setBounds] = useState<UploadResponse["bounds"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const uploadFile = async (
    file: File,
    options: {
      numColors: number;
      targetWidthMm: number;
      machineKey: string;
      removeBackground: boolean;
    },
  ) => {
    if (!file) return;
    const id = ++requestId.current;

    const url = new URL(uploadUrl, window.location.href);
    url.searchParams.set("num_colors", options.numColors.toString());
    url.searchParams.set("target_width_mm", options.targetWidthMm.toString());
    url.searchParams.set("machine_key", options.machineKey);
    url.searchParams.set("remove_background", options.removeBackground.toString());

    const formData = new FormData();
    formData.append("file", file);

    try {
      setIsLoading(true);

      const response = await fetch(url.toString(), {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : `Upload failed (${response.status})`);
      }

      const data: UploadResponse = await response.json();
      if (id !== requestId.current) return;

      setBase64File(data.file_base64);
      setFormat(data.format);
      setPreview(data.preview);
      setBounds(data.bounds);
    } catch (err) {
      if (id !== requestId.current) return;
      const errorMessage =
        err instanceof Error ? err.message : "An unexpected error occurred";
      setError(errorMessage);
      console.error(err);
    } finally {
      if (id === requestId.current) setIsLoading(false);
    }
  };

  const resetFileUpload = () => {
    requestId.current++;
    setBase64File(null);
    setFormat(null);
    setError(null);
    setPreview(null);
    setBounds(null);
    setIsLoading(false);
  };

  return {
    base64File,
    format,
    preview,
    bounds,
    isLoading,
    error,
    uploadFile,
    resetFileUpload,
  };
}
