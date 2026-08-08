import { useState } from "react";

interface UploadResponse {
  file_base64: any;
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
  base64File: any;
  preview: Array<{
    color: string;
    stitches: Array<[number, number, number]>;
  }> | null;
  error: string | null;
  bounds: {
    widthUnits: number | null;
    heightUnits: number | null;
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
  } | null;
  uploadFile: (file: File) => Promise<void>;
  resetFileUpload: () => void;
}

export function useFileUpload(uploadUrl: string): UseFileUploadReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [base64File, setBase64File] = useState<any | null>(null);
  const [preview, setPreview] = useState<UploadResponse["preview"]>(null);
  const [bounds, setBounds] = useState<UploadResponse["bounds"]>(null);
  const [error, setError] = useState<string | null>(null);

  const uploadFile = async (file: File) => {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      setIsLoading(true);

      const response = await fetch(uploadUrl, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed with status: ${response.status}`);
      }

      const data: UploadResponse = await response.json();
      console.log(data);
      setBase64File(data.file_base64);
      setPreview(data.preview);
      setBounds(data.bounds);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "An unexpected error occurred";
      setError(errorMessage);
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const resetFileUpload = () => {
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
