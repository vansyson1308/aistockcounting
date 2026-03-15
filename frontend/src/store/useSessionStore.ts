import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface SessionState {
  staffId: string;
  trayIdPrefix: string;
  setStaffId: (id: string) => void;
  setTrayIdPrefix: (prefix: string) => void;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      staffId: '',
      trayIdPrefix: '',
      setStaffId: (id) => set({ staffId: id }),
      setTrayIdPrefix: (prefix) => set({ trayIdPrefix: prefix }),
    }),
    { name: 'vjsc-session' }
  )
);
