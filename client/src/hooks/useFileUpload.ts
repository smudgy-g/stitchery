import { useRef, useState } from "react";

interface UploadResponse {
  file_base64: string;
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
      hoopKey: string;
    },
  ) => Promise<void>;
  resetFileUpload: () => void;
}

export function useFileUpload(uploadUrl: string): UseFileUploadReturn {
  const requestId = useRef(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [base64File, setBase64File] = useState<string | null>(null);
  const [preview, setPreview] = useState<UploadResponse["preview"] | null>(null);
  const [bounds, setBounds] = useState<UploadResponse["bounds"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const uploadFile = async (
    file: File,
    options: {
      numColors: number;
      targetWidthMm: number;
      hoopKey: string;
    },
  ) => {
    if (!file) return;
    const id = ++requestId.current;

    const url = new URL(uploadUrl);
    url.searchParams.set("num_colors", options.numColors.toString());
    url.searchParams.set("target_width_mm", options.targetWidthMm.toString());
    url.searchParams.set("hoop_key", options.hoopKey);

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
    setError(null);
    setPreview(null);
    setBounds(null);
    setIsLoading(false);
  };

  return {
    base64File,
    preview,
    bounds,
    isLoading,
    error,
    uploadFile,
    resetFileUpload,
  };
}
