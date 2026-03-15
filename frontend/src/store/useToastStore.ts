import { create } from 'zustand';

type ToastVariant = 'success' | 'warning' | 'error';

interface ToastState {
  message: string;
  visible: boolean;
  variant: ToastVariant;
  show: (message: string, duration?: number, variant?: ToastVariant) => void;
  hide: () => void;
}

let timer: ReturnType<typeof setTimeout> | null = null;

export const useToastStore = create<ToastState>()((set) => ({
  message: '',
  visible: false,
  variant: 'success',
  show: (message, duration = 3000, variant = 'success') => {
    if (timer) clearTimeout(timer);
    set({ message, visible: true, variant });
    timer = setTimeout(() => {
      set({ visible: false });
      timer = null;
    }, duration);
  },
  hide: () => {
    if (timer) clearTimeout(timer);
    set({ visible: false });
    timer = null;
  },
}));
