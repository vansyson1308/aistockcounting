'use client';

import { useRef, useState } from 'react';

type Props = { onCapture: (file: File, previewUrl: string) => void };

export default function CameraCapture({ onCapture }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [enabled, setEnabled] = useState(false);

  const startCamera = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      setEnabled(true);
    }
  };

  const capture = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const file = new File([blob], `capture-${Date.now()}.jpg`, { type: 'image/jpeg' });
      onCapture(file, URL.createObjectURL(blob));
    }, 'image/jpeg', 0.9);
  };

  return (
    <div className="space-y-3">
      <button type="button" className="w-full rounded-xl bg-indigo-600 p-3 text-white" onClick={startCamera}>
        Mở camera
      </button>
      <video ref={videoRef} autoPlay playsInline className={`w-full rounded-xl ${enabled ? 'block' : 'hidden'}`} />
      <canvas ref={canvasRef} className="hidden" />
      {enabled && (
        <button type="button" className="w-full rounded-xl bg-slate-800 p-3 text-white" onClick={capture}>
          Chụp ảnh
        </button>
      )}
    </div>
  );
}
