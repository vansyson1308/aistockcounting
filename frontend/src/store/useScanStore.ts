import { create } from 'zustand';
import { CountResult } from '@/types';

interface ScanState {
  file: File | null;
  preview: string;
  result: CountResult | null;
  manualCount: number | '';
  isAICorrect: boolean | null;
  notes: string;
  loading: boolean;
  status: string;
  setFile: (file: File | null, preview?: string) => void;
  setResult: (result: CountResult | null) => void;
  setManualCount: (count: number | '') => void;
  setIsAICorrect: (correct: boolean | null) => void;
  setNotes: (notes: string) => void;
  setLoading: (loading: boolean) => void;
  setStatus: (status: string) => void;
  reset: () => void;
}

const initialState = {
  file: null,
  preview: '',
  result: null,
  manualCount: '' as number | '',
  isAICorrect: null as boolean | null,
  notes: '',
  loading: false,
  status: '',
};

export const useScanStore = create<ScanState>()((set) => ({
  ...initialState,
  setFile: (file, preview) =>
    set({
      file,
      preview: preview || (file ? URL.createObjectURL(file) : ''),
      result: null,
      status: '',
    }),
  setResult: (result) =>
    set({
      result,
      manualCount: result?.detected_count ?? '',
      status: result
        ? `AI đếm ${result.detected_count} món (${result.processing_time_ms}ms).`
        : '',
    }),
  setManualCount: (manualCount) => set({ manualCount }),
  setIsAICorrect: (isAICorrect) => set({ isAICorrect }),
  setNotes: (notes) => set({ notes }),
  setLoading: (loading) => set({ loading }),
  setStatus: (status) => set({ status }),
  reset: () => set({ ...initialState, status: 'Sẵn sàng kiểm kê khay tiếp theo.' }),
}));
