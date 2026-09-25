import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/** A scan escalated from this device. There is no server-side list endpoint for the queue. */
export type QueuedReview = {
  id: string;
  branchCode: string;
  trayCode: string;
  agentCount: number | null;
  expectedCount: number | null;
  createdAt: string;
};

const MAX_ITEMS = 30;

interface ReviewQueueState {
  items: QueuedReview[];
  add: (item: QueuedReview) => void;
  remove: (id: string) => void;
}

export const useReviewQueueStore = create<ReviewQueueState>()(
  persist(
    (set) => ({
      items: [],
      add: (item) =>
        set((state) => ({
          items: [item, ...state.items.filter((i) => i.id !== item.id)].slice(0, MAX_ITEMS),
        })),
      remove: (id) => set((state) => ({ items: state.items.filter((i) => i.id !== id) })),
    }),
    { name: 'vjsc-review-queue' }
  )
);
