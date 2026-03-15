export function getImageDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      resolve({ width: img.width, height: img.height });
      URL.revokeObjectURL(img.src);
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

export async function compressImage(
  file: File,
  maxWidth = 1920,
  quality = 0.85
): Promise<File> {
  const { width, height } = await getImageDimensions(file);

  // No compression needed if already small
  if (width <= maxWidth && file.size < 500_000) {
    return file;
  }

  const scale = width > maxWidth ? maxWidth / width : 1;
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);

  const ctx = canvas.getContext('2d');
  if (!ctx) return file;

  const img = await createImageBitmap(file);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', quality)
  );

  if (!blob || blob.size >= file.size) return file;

  return new File([blob], file.name.replace(/\.\w+$/, '.jpg'), {
    type: 'image/jpeg',
  });
}
