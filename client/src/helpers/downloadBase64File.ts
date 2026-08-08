export const downloadBase64File = (
  base64Data: string,
  fileName: string,
  mimeType: string = "application/octet-stream",
) => {
  const base64Clean = base64Data.includes(",")
    ? base64Data.split(",")[1]
    : base64Data;

  let finalMimeType = mimeType;
  if (base64Data.startsWith("data:")) {
    const matchedMime = base64Data.match(/data:(.*?);base64/);
    if (matchedMime && matchedMime[1]) {
      finalMimeType = matchedMime[1];
    }
  }

  const byteChars = atob(base64Clean);
  const byteNumbers = new Array(byteChars.length);

  for (let i = 0; i < byteChars.length; i++) {
    byteNumbers[i] = byteChars.charCodeAt(i);
  }

  const byteArray = new Uint8Array(byteNumbers);

  const blob = new Blob([byteArray], { type: finalMimeType });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();

  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
