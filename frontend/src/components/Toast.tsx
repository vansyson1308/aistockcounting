'use client';

import { useToastStore } from '@/store/useToastStore';

type Props = { message: string; show: boolean };

export default function Toast({ message, show }: Props) {
  if (!show) return null;
  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full bg-emerald-600 px-4 py-2 text-sm text-white shadow">
      {message}
    </div>
  );
}

const variantStyles = {
  success: 'bg-emerald-600',
  warning: 'bg-amber-500',
  error: 'bg-red-600',
};

export function GlobalToast() {
  const { message, visible, variant, hide } = useToastStore();

  if (!visible) return null;

  return (
    <div
      className={`fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl px-5 py-3 text-sm font-medium text-white shadow-lg ${variantStyles[variant]}`}
    >
      <span>{message}</span>
      <button
        onClick={hide}
        className="ml-3 text-white/80 hover:text-white"
        aria-label="Đóng"
      >
        ✕
      </button>
    </div>
  );
}
