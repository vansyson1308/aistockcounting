'use client';

type Props = {
  manualCount: number | '';
  setManualCount: (v: number | '') => void;
  isAICorrect: boolean | null;
  setIsAICorrect: (v: boolean | null) => void;
  notes: string;
  setNotes: (v: string) => void;
};

export default function ManualOverride(props: Props) {
  return (
    <div className="space-y-3 rounded-xl bg-white p-4 shadow dark:bg-slate-800">
      <label className="block text-sm font-medium">Số lượng chỉnh sửa</label>
      <input
        type="number"
        min={0}
        value={props.manualCount}
        onChange={(e) => props.setManualCount(e.target.value === '' ? '' : Number(e.target.value))}
        placeholder="Nhập số lượng thực tế"
        className="w-full rounded-lg border border-slate-300 p-3 dark:border-slate-600 dark:bg-slate-700"
      />

      <label className="block text-sm font-medium">AI dự đoán đúng?</label>
      <div className="flex gap-2">
        <button
          className={`flex-1 rounded-lg border p-3 ${props.isAICorrect === true ? 'bg-emerald-600 text-white' : 'bg-white dark:bg-slate-700'}`}
          onClick={() => props.setIsAICorrect(true)}
          type="button"
        >
          Đúng
        </button>
        <button
          className={`flex-1 rounded-lg border p-3 ${props.isAICorrect === false ? 'bg-rose-600 text-white' : 'bg-white dark:bg-slate-700'}`}
          onClick={() => props.setIsAICorrect(false)}
          type="button"
        >
          Sai
        </button>
      </div>

      <label className="block text-sm font-medium">Ghi chú</label>
      <textarea
        value={props.notes}
        onChange={(e) => props.setNotes(e.target.value)}
        placeholder="Ví dụ: món ở góc bị che"
        className="min-h-24 w-full rounded-lg border border-slate-300 p-3 dark:border-slate-600 dark:bg-slate-700"
      />
    </div>
  );
}
