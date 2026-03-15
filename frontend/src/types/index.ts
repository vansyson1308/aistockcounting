export type Box = { x: number; y: number; w: number; h: number; conf: number };

export type ApiError = { code: string; message: string };

export type ApiEnvelope<T> = {
  success: boolean;
  data: T;
};

export type CountResult = {
  image_path: string;
  image_thumbnail?: string | null;
  detected_count: number;
  confidence_avg: number;
  processing_time_ms: number;
  boxes: Box[];
  tray_id?: string | null;
  staff_id?: string | null;
  mock_mode?: boolean;
  model_version?: string;
};

export type SavePayload = {
  image_path: string;
  image_thumbnail?: string | null;
  detected_count: number;
  manual_count?: number | null;
  confidence_avg?: number | null;
  boxes_json: Box[];
  staff_id?: string | null;
  tray_id?: string | null;
  is_ai_correct?: boolean | null;
  notes?: string | null;
};

export type HistoryItem = {
  id: string;
  image_path: string;
  image_thumbnail?: string | null;
  detected_count: number;
  manual_count?: number | null;
  confidence_avg?: number | null;
  staff_id?: string | null;
  tray_id?: string | null;
  is_ai_correct?: boolean | null;
  notes?: string | null;
  boxes_json?: Box[] | null;
  created_at: string;
};

export type HistoryResponseData = {
  items: HistoryItem[];
  page: number;
  limit: number;
  total: number;
};

export type StatsData = {
  total_records: number;
  avg_detected_count: number;
  avg_manual_count: number;
  ai_correct_rate: number;
};
