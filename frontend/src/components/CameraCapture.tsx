'use client';

import { useEffect, useRef, useState } from 'react';

type Props = { onCapture: (file: File, previewUrl: string) => void };

export default function CameraCapture({ onCapture }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const video = videoRef.current;
    return () => {
      const stream = video?.srcObject as MediaStream | null;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const startCamera = async () => {
    setError('');
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('unsupported');
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        setEnabled(true);
      }
    } catch {
      setError('Could not open the camera. Allow camera access or upload a photo instead.');
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
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const file = new File([blob], `capture-${Date.now()}.jpg`, { type: 'image/jpeg' });
        onCapture(file, URL.createObjectURL(blob));
      },
      'image/jpeg',
      0.85
    );
  };

  return (
    <div className="space-y-3">
      <button
        type="button"
        className="w-full rounded-xl bg-indigo-600 p-3 text-white"
        onClick={startCamera}
      >
        Open camera
      </button>
      {error && (
        <p role="alert" className="text-sm text-rose-700 dark:text-rose-300">
          {error}
        </p>
      )}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        aria-label="Camera preview"
        className={`w-full rounded-xl ${enabled ? 'block' : 'hidden'}`}
      />
      <canvas ref={canvasRef} className="hidden" />
      {enabled && (
        <button
          type="button"
          className="w-full rounded-xl bg-slate-800 p-3 text-white"
          onClick={capture}
        >
          Take photo
        </button>
      )}
    </div>
  );
}
