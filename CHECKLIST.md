# PRD Acceptance Criteria Verification Checklist (E2E)

> Goal: verify MVP behavior end-to-end with Docker Compose stack (`make up`) and Nginx routing.

## Preconditions
1. `cp .env.example .env`
2. `make up`
3. `make bootstrap` (optional safety; also auto-run by db init SQL)

| # | Acceptance Criteria (PRD) | How to test | Expected result |
|---|---|---|---|
| 1 | Upload ảnh thành công | Tại `/scan`, dùng camera hoặc chọn file JPG/PNG rồi nhấn **Đếm bằng AI**. Hoặc chạy `./scripts/upload_sample.sh scripts/generated_sample.jpg`. | Backend nhận multipart, trả JSON `success=true` kèm `image_path`. |
| 2 | AI trả kết quả đếm (< 5s) | Quan sát phản hồi `/count-items` (field `processing_time_ms`) ở MOCK_MODE và đo thời gian thực tế request. | Có `detected_count`, `boxes`, `confidence_avg`, `processing_time_ms`; trong MOCK_MODE thường < 5s. |
| 3 | Hiển thị bounding boxes | Sau khi đếm ở `/scan`, quan sát khung xanh trên ảnh; vào `/history/{id}` quan sát lại overlay. | Box hiển thị đúng tỷ lệ theo ảnh hiển thị (scaled overlay). |
| 4 | Manual override | Trên `/scan`, nhập `manual_count`, chọn AI đúng/sai, nhập ghi chú rồi lưu. | Dữ liệu manual được gửi trong payload `/save`. |
| 5 | Lưu thành công | Bấm **Lưu** trên `/scan`. | Toast thành công; record có trong DB và xuất hiện ở `/history`. |
| 6 | Xem lịch sử | Vào `/history`, lọc theo date/staff/tray/ai_correct, phân trang. | Danh sách thay đổi theo filter; phân trang hoạt động. |
| 7 | AI accuracy | Chạy model thật (không MOCK_MODE) trên test set nội bộ. | Đạt mAP/accuracy theo PRD UAT (ngoài phạm vi CI). |
| 8 | Mobile responsive | Mở app ở viewport 375–428px (DevTools). | UI không vỡ layout, nút thao tác dễ bấm. |
| 9 | Performance | Theo dõi network timings cho `/count-items`, `/save`, `/history`. | API thường < 5s ở MOCK_MODE; không crash khi thao tác lặp lại. |
| 10 | Deployment | Chạy full stack bằng compose + nginx. | Truy cập được qua `http://localhost`, `/api/` hoạt động, healthchecks pass. |

## DB admin note
- Xem nhanh bản ghi:
  - `docker compose exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "select id, tray_id, staff_id, detected_count, manual_count, created_at from counts order by created_at desc limit 20;"`

## Utility scripts
- Tạo ảnh mẫu: `./scripts/gen_sample_image.py`
- Upload test nhanh: `./scripts/upload_sample.sh scripts/generated_sample.jpg`
- Smoke checklist trợ giúp: `./scripts/e2e_smoke.sh`
