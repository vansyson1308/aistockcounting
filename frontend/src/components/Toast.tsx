'use client';

type Props = { message: string; show: boolean };

export default function Toast({ message, show }: Props) {
  if (!show) return null;
  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full bg-emerald-600 px-4 py-2 text-sm text-white shadow">
      {message}
    </div>
  );
}
