
VIETJEWELERS
AI STOCK COUNTING SYSTEM

Technical Specification Document
Tài liệu Đặc tả Kỹ thuật

MVP Version 0.1

Document ID	VJ-TSD-2026-001
Version	1.0
Date	February 2026
Author	VietJewelers Project Team
Classification	Internal – Developer Handoff
 
TABLE OF CONTENTS
1.  Executive Summary (Tóm tắt dự án)
2.  System Architecture (Kiến trúc hệ thống)
3.  Tech Stack & Environment
4.  Database Schema
5.  API Specification
6.  AI Model Requirements
7.  Frontend Requirements
8.  Business Rules (Quy tắc nghiệp vụ)
9.  Deployment & Infrastructure
10.  Development Timeline
11.  Acceptance Criteria
12.  Future Roadmap
 
1. Executive Summary
Tóm tắt dự án

1.1 Problem Statement
VietJewelers hiện đang thực hiện kiểm kê tồn kho trang sức hàng ngày theo quy trình thủ công: nhân viên chụp ảnh từng khay → đếm bằng mắt → ghi số lên ảnh → gửi nhóm chat → nhập Google Sheet. Quy trình này tốn thời gian, dễ sai sót, không mở rộng được và khó theo dõi chênh lệch.
1.2 Solution
Xây dựng hệ thống AI Stock Counting sử dụng computer vision (đặc biệt là YOLO object detection) để tự động đếm số lượng trang sức trên mỗi khay từ ảnh chụp, thay thế toàn bộ quy trình đếm thủ công.
1.3 MVP Scope
MVP v0.1 tập trung vào một chức năng duy nhất: AI đếm số lượng món trang sức trong ảnh khay, kèm khả năng nhân viên sửa số liệu và xem lịch sử. Không bao gồm: nhận dạng SKU, so sánh chênh lệch, tích hợp KiotViet.
Attribute	Detail
Project Name	VietJewelers AI Stock Counting System
Version	MVP v0.1
Core Function	AI-powered jewelry counting from tray photos
Target Users	VietJewelers store staff
Platform	Mobile-first Progressive Web App (PWA)
AI Model	YOLOv8/v9 – Single class detection
Training Data	80–150 labeled tray photos
Expected Accuracy	70–85% (improving with retraining cycle)
 
2. System Architecture
Kiến trúc hệ thống

2.1 Architecture Overview
Hệ thống sử dụng kiến trúc 3 tầng (đơn giản, phù hợp MVP):
FRONTEND
React / Next.js PWA
Mobile-first UI
Camera / Upload	BACKEND
Python FastAPI
REST API Endpoints
YOLO Inference	STORAGE
PostgreSQL
S3 / MinIO (Images)
YOLO Model Weights

2.2 Data Flow
Luồng dữ liệu chính của hệ thống:
•	Staff chụp/upload ảnh khay trang sức từ điện thoại (Frontend)
•	Ảnh được gửi đến Backend qua POST /api/v1/count-items (multipart/form-data)
•	Backend lưu ảnh vào S3/MinIO, chạy YOLO inference
•	Kết quả (số lượng + bounding boxes) trả về Frontend
•	Staff xem kết quả, sửa nếu cần, nhấn Save
•	Hệ thống lưu record vào PostgreSQL qua POST /api/v1/save
•	Staff có thể xem lịch sử qua GET /api/v1/history
 
3. Tech Stack & Environment

Layer	Technology	Justification
Frontend	Next.js 14+ (React)	Mobile-first, PWA support, SSR cho SEO nếu cần, ecosystem lớn
UI Framework	Tailwind CSS	Rapid prototyping, responsive design, nhẹ và nhanh
Backend	Python FastAPI	Hệ sinh thái AI/ML tốt nhất, async native, auto-docs (Swagger)
AI Model	YOLOv8 (Ultralytics)	State-of-the-art detection, Python native, dễ train/deploy
Database	PostgreSQL 16	Ổn định, hỗ trợ JSON, query mạnh, free
Image Storage	MinIO (self-host) hoặc Cloudflare R2	S3-compatible, chi phí thấp, dễ migrate lên AWS sau
Containerization	Docker + Docker Compose	Môi trường nhất quán, deploy dễ dàng
Reverse Proxy	Nginx	HTTPS, load balancing, static file serving
CI/CD	GitHub Actions (optional)	Auto test + deploy khi push code

3.1 Environment Requirements
Requirement	Specification
Python Version	3.10+
Node.js Version	18 LTS+
Server Minimum	2 vCPU, 4GB RAM, 50GB SSD (VPS)
GPU	Không bắt buộc cho MVP (CPU inference chấp nhận được)
OS	Ubuntu 22.04 LTS
Domain	stock.vietjewelers.com (hoặc subdomain tương tự)
SSL	Let’s Encrypt (free, auto-renew)
 
4. Database Schema

4.1 Table: counts
Bảng chính lưu kết quả đếm của mỗi lần kiểm kê.
Column	Type	Nullable	Description
id	UUID	NO	Primary key, auto-generated (UUID v4)
image_path	VARCHAR(500)	NO	Đường dẫn ảnh trên S3/MinIO
image_thumbnail	VARCHAR(500)	YES	Thumbnail path (cho hiển thị nhanh ở history)
detected_count	INTEGER	NO	Số lượng AI đếm được
manual_count	INTEGER	YES	Số lượng nhân viên sửa (NULL = chấp nhận kết quả AI)
confidence_avg	FLOAT	YES	Confidence trung bình của model
boxes_json	JSONB	YES	Bounding boxes data [{x,y,w,h,conf}]
staff_id	VARCHAR(50)	YES	Mã nhân viên
tray_id	VARCHAR(50)	YES	Mã khay (nếu có)
is_ai_correct	BOOLEAN	YES	Staff đánh dấu AI đúng/sai (cho retraining)
notes	TEXT	YES	Ghi chú của nhân viên
created_at	TIMESTAMP	NO	Thời điểm tạo record (UTC)
updated_at	TIMESTAMP	NO	Thời điểm cập nhật cuối

4.2 Indexes
•	idx_counts_created_at ON counts(created_at DESC) — Query lịch sử theo ngày
•	idx_counts_staff_id ON counts(staff_id) — Filter theo nhân viên
•	idx_counts_tray_id ON counts(tray_id) — Filter theo khay
•	idx_counts_is_ai_correct ON counts(is_ai_correct) WHERE is_ai_correct = false — Partial index cho retraining data

4.3 SQL Migration Script
Developer cần tạo migration file với nội dung sau:
CREATE TABLE counts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  image_path VARCHAR(500) NOT NULL,
  image_thumbnail VARCHAR(500),
  detected_count INTEGER NOT NULL DEFAULT 0,
  manual_count INTEGER,
  confidence_avg FLOAT,
  boxes_json JSONB,
  staff_id VARCHAR(50),
  tray_id VARCHAR(50),
  is_ai_correct BOOLEAN,
  notes TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
 
CREATE INDEX idx_counts_created_at
  ON counts(created_at DESC);
CREATE INDEX idx_counts_staff_id
  ON counts(staff_id);
CREATE INDEX idx_counts_tray_id
  ON counts(tray_id);
CREATE INDEX idx_counts_ai_wrong
  ON counts(is_ai_correct) WHERE is_ai_correct = false;
 
5. API Specification

Base URL: /api/v1
Format: JSON (trừ file upload dùng multipart/form-data)

5.1 POST /api/v1/count-items
Chạy AI detection trên ảnh khay, trả về số lượng và bounding boxes.
Request
Field	Type	Required	Description
image	File	Yes	Ảnh khay trang sức (JPEG/PNG, max 10MB)
tray_id	String	No	Mã khay (nếu staff muốn gắn tag)
staff_id	String	No	Mã nhân viên

Response (200 OK)
{
  "success": true,
  "data": {
    "count": 12,
    "confidence_avg": 0.87,
    "boxes": [
      {
        "x": 120, "y": 85,
        "width": 45, "height": 50,
        "confidence": 0.92,
        "label": "item"
      }
    ],
    "image_path": "/images/2026/02/abc123.jpg",
    "processing_time_ms": 340
  }
}

5.2 POST /api/v1/save
Lưu kết quả kiểm kê vào database (sau khi staff review xong).
Request Body (JSON)
{
  "image_path": "/images/2026/02/abc123.jpg",
  "detected_count": 12,
  "manual_count": 13,
  "confidence_avg": 0.87,
  "boxes_json": [...],
  "staff_id": "NV001",
  "tray_id": "TRAY-A3",
  "is_ai_correct": false,
  "notes": "AI bo sot 1 mat day phia goc trai"
}

5.3 GET /api/v1/history
Lấy danh sách lịch sử kiểm kê, hỗ trợ pagination và filter.
Query Parameters
Param	Type	Default	Description
page	Integer	1	Số trang
limit	Integer	20	Số record/trang (max 100)
date_from	Date	—	Filter từ ngày (YYYY-MM-DD)
date_to	Date	—	Filter đến ngày
staff_id	String	—	Filter theo nhân viên
tray_id	String	—	Filter theo khay
ai_correct	Boolean	—	Filter theo AI đúng/sai

5.4 GET /api/v1/stats
Thống kê tổng quan (cho dashboard đơn giản).
Response
{
  "today_scans": 24,
  "today_total_items": 312,
  "ai_accuracy_rate": 0.82,
  "corrections_today": 5,
  "total_scans_all_time": 1450
}

5.5 Error Handling
Tất cả API trả về format error thống nhất:
{
  "success": false,
  "error": {
    "code": "INVALID_IMAGE",
    "message": "File is not a valid image format"
  }
}

HTTP Code	Error Code	Description
400	INVALID_IMAGE	Ảnh không hợp lệ (sai format, quá lớn)
400	MISSING_REQUIRED_FIELD	Thiếu trường bắt buộc
404	RECORD_NOT_FOUND	Không tìm thấy record
500	MODEL_ERROR	Lỗi khi chạy AI model
500	STORAGE_ERROR	Lỗi lưu ảnh
 
6. AI Model Requirements

6.1 Model Specification
Parameter	Value
Architecture	YOLOv8n (nano) hoặc YOLOv8s (small) — bắt đầu với nano cho tốc độ
Framework	Ultralytics (pip install ultralytics)
Classes	1 class duy nhất: "item"
Training Data	80–150 ảnh labeled (YOLO format)
Image Size	640x640 (resize tự động khi train)
Batch Size	16 (tuỳ vào RAM/VRAM)
Epochs	100–300 với early stopping (patience=50)
Augmentation	Built-in Ultralytics augmentation (flip, rotate, mosaic)
Export Format	ONNX (cho production inference nhanh hơn)
Inference Time Target	< 2 giây/ảnh trên CPU
Confidence Threshold	0.25 (default, có thể điều chỉnh)
NMS IoU Threshold	0.45 (tránh đếm trùng)

6.2 Training Pipeline
Developer cần setup pipeline sau:
•	Thu thập 80–150 ảnh từ VietJewelers staff (các khay thực tế, đa dạng góc chụp và ánh sáng)
•	Label bằng Roboflow, LabelImg hoặc CVAT — theo Labeling Guideline PDF đã cung cấp
•	Split data: 70% train / 20% validation / 10% test
•	Train với Ultralytics CLI: yolo detect train data=dataset.yaml model=yolov8n.pt epochs=200
•	Evaluate: mAP@0.5 mục tiêu > 0.7 cho MVP
•	Export: yolo export model=best.pt format=onnx
•	Integration test: chạy inference trên 10 ảnh test, verify count accuracy

6.3 Inference Code Template
from ultralytics import YOLO
import cv2
 
model = YOLO("models/best.onnx")  # or best.pt
 
def count_items(image_path: str, conf=0.25, iou=0.45):
    results = model.predict(
        source=image_path,
        conf=conf,
        iou=iou,
        verbose=False
    )
    boxes = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            boxes.append({
                "x": int(x1), "y": int(y1),
                "width": int(x2 - x1),
                "height": int(y2 - y1),
                "confidence": round(float(box.conf[0]), 3)
            })
    return {
        "count": len(boxes),
        "confidence_avg": round(
            sum(b["confidence"] for b in boxes) / max(len(boxes), 1), 3
        ),
        "boxes": boxes
    }
 
7. Frontend Requirements

7.1 Pages & Components
Page/Route	Components	Functionality
/	HomePage	Landing page với 2 nút chính: “Kiểm kê mới” và “Xem lịch sử”
/scan	ScanPage, CameraCapture, ResultDisplay, ManualOverride	Chụp/upload ảnh → hiển thị kết quả AI + bounding boxes → sửa số → lưu
/history	HistoryList, FilterBar, RecordCard	Danh sách kiểm kê đã lưu, filter theo ngày/khay/nhân viên
/history/:id	RecordDetail	Xem chi tiết 1 record: ảnh gốc + boxes + số liệu

7.2 UI/UX Requirements
•	Mobile-first: 100% responsive, tối ưu cho màn hình 375–428px (iPhone SE – iPhone 15 Pro Max)
•	Camera access: dùng navigator.mediaDevices.getUserMedia() cho chụp trực tiếp
•	Image preview: hiển thị ảnh với bounding boxes overlay (canvas hoặc SVG)
•	Loading state: spinner/skeleton khi AI đang xử lý (ước tính 1–2 giây)
•	Offline indicator: thông báo khi mất kết nối
•	Touch-friendly: nút tối thiểu 44x44px, khoảng cách đủ
•	Ngôn ngữ: Tiếng Việt là chính (UI labels, messages, placeholders)

7.3 Scan Page Flow (Chi tiết)
Trang chính của ứng dụng — developer cần implement đúng flow sau:
Step	UI State	Behavior
1	Camera/Upload	Hiển 2 option: chụp ảnh (camera) hoặc chọn từ gallery. Optional: nhập tray_id.
2	Processing	Hiển ảnh preview + loading spinner + text “Đang phân tích...”
3	Result Display	Hiển ảnh với bounding boxes overlay. Hiển số lượng lớn rõ ràng. Hiển confidence trung bình.
4	Manual Override	Input số để staff sửa. Toggle “AI đúng/sai”. Textbox ghi chú (optional).
5	Save & Confirm	Nút “Lưu” gửi POST /save. Toast/alert xác nhận thành công. Option: scan khay tiếp theo.
 
8. Business Rules (Quy tắc nghiệp vụ)

Cực kỳ quan trọng: đây là các quy tắc đếm đặc thù của VietJewelers. AI model phải được train theo đúng các quy tắc này (thông qua labeling), và staff cũng sửa số liệu dựa trên các quy tắc này.

Loại trang sức	Số items	Giải thích chi tiết
Mặt dây chỉ móc vào dây chuyền (1 chốt)	2	Mặt dây và dây chuyền được đếm riêng vì có thể tháo rời → label 2 box
Mặt dây hàn liền dây (2 chốt)	1	Mặt và dây không tháo được → label 1 box bao toàn bộ
Nhiều mặt dây trên 1 móc	Mỗi mặt = 1	Đếm từng mặt dây riêng biệt, không đếm móc
Bông tai	Mỗi bên = 1	1 đôi bông tai = 2 items (trái + phải)
Vòng tay / lắc chân có charm nhỏ	1	Đếm là 1 item duy nhất, không đếm charm riêng
Nhẫn	1/nhẫn	Mỗi chiếc nhẫn = 1 item

Lưu ý cho Developer: Trong MVP v0.1, model chỉ có 1 class là “item”. Các quy tắc trên được thực thi thông qua cách label data (mỗi box = 1 item theo quy tắc). AI không cần phân biệt loại trang sức — chỉ cần detect đúng vị trí và số lượng box.
 
9. Deployment & Infrastructure

9.1 Docker Compose Structure
Toàn bộ hệ thống được đóng gói trong Docker Compose với các service sau:
Service	Image	Port	Description
frontend	node:18	3000	Next.js app (SSR + static)
backend	python:3.10	8000	FastAPI + YOLO inference
db	postgres:16	5432	PostgreSQL database
minio	minio/minio	9000/9001	S3-compatible image storage
nginx	nginx:alpine	80/443	Reverse proxy + SSL termination

9.2 File Structure (Đề xuất)
vietjewelers-stock/
├── docker-compose.yml
├── nginx/
│   └── nginx.conf
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Settings & env vars
│   │   ├── models/
│   │   │   └── detection.py     # YOLO inference logic
│   │   ├── routes/
│   │   │   ├── count.py         # POST /count-items
│   │   │   ├── save.py          # POST /save
│   │   │   ├── history.py       # GET /history
│   │   │   └── stats.py         # GET /stats
│   │   ├── database.py          # DB connection & queries
│   │   └── storage.py           # S3/MinIO operations
│   └── models/
│       └── best.onnx            # Trained YOLO model
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── pages/
│       │   ├── index.tsx          # Home
│       │   ├── scan.tsx           # Scan page
│       │   └── history.tsx        # History page
│       ├── components/
│       │   ├── CameraCapture.tsx
│       │   ├── ResultDisplay.tsx
│       │   ├── ManualOverride.tsx
│       │   ├── HistoryList.tsx
│       │   └── BoundingBoxOverlay.tsx
│       └── lib/
│           └── api.ts               # API client
└── training/
    ├── dataset/                 # Labeled images (YOLO format)
    ├── dataset.yaml             # YOLO dataset config
    └── train.py                 # Training script

9.3 Environment Variables
Variable	Example	Description
DATABASE_URL	postgresql://...	PostgreSQL connection string
MINIO_ENDPOINT	minio:9000	MinIO server address
MINIO_ACCESS_KEY	minioadmin	MinIO access key
MINIO_SECRET_KEY	***	MinIO secret key
MINIO_BUCKET	tray-images	Bucket name cho ảnh
MODEL_PATH	./models/best.onnx	Đường dẫn model YOLO
CONFIDENCE_THRESHOLD	0.25	Ngưỡng confidence
MAX_IMAGE_SIZE_MB	10	Giới hạn file upload
CORS_ORIGINS	https://stock.vj.com	Allowed origins
 
10. Development Timeline

Tổng thời gian ước tính: 3–4 tuần (1 developer full-time)

Tuần	Focus	Deliverables
1	Data & AI Model	Thu thập + label 80–150 ảnh. Train YOLOv8. Đạt mAP > 0.7. Export ONNX model.
2	Backend + Integration	Setup FastAPI + PostgreSQL + MinIO. Implement 4 endpoints. Tích hợp YOLO inference. Viết unit tests.
3	Frontend + Testing	Build Next.js PWA: Scan page, History page, Result display với bounding boxes. Test với ảnh thực tế từ cửa hàng. Fix accuracy issues.
4	Deploy + UAT	Docker Compose deployment. Nginx + SSL setup. Staff testing trong workflow thực tế. Thu thập feedback cho v0.2.
 
11. Acceptance Criteria
Tiêu chí nghiệm thu

Hệ thống được nghiệm thu khi đạt TẤT CẢ các tiêu chí sau:

#	Tiêu chí	Chi tiết kiểm tra
1	Upload ảnh thành công	Staff có thể chụp hoặc upload ảnh từ điện thoại, hệ thống nhận được và xử lý
2	AI trả kết quả đếm	Sau khi upload, AI trả về số lượng + bounding boxes trong < 5 giây
3	Hiển thị bounding boxes	Ảnh hiển thị với các khung bao quanh items được detect
4	Manual override	Staff có thể sửa số lượng, đánh dấu AI đúng/sai, thêm ghi chú
5	Lưu thành công	Record được lưu vào database và xuất hiện trong history
6	Xem lịch sử	History page hiển thị danh sách, filter được theo ngày, có pagination
7	AI accuracy	mAP@0.5 ≥ 0.7 trên test set. Counting accuracy ≥ 70% trên ảnh thực tế
8	Mobile responsive	Hoạt động tốt trên iPhone và Android (Chrome, Safari)
9	Performance	Page load < 3s. API response < 5s. Không crash khi sử dụng liên tục
10	Deployment	Hệ thống chạy ổn định trên VPS, có HTTPS, staff truy cập được từ điện thoại
 
12. Future Roadmap

Sau khi MVP v0.1 hoạt động ổn định, hệ thống sẽ được nâng cấp theo lộ trình:

Version	Feature	Description
v0.2	Tray Discrepancy Detection	So sánh số lượng hôm nay vs hôm qua. Flag khay có thay đổi bất thường.
v0.3	Per-slot Detection	Nhận dạng từng ô trên khay (khay có lưới cố định). Xác định ô trống/đầy.
v0.4	SKU Recognition	AI nhận dạng từng món theo mã SKU. Gắn tag SKU vào mỗi bounding box.
v0.5	KiotViet Integration	Đối soát với hệ thống KiotViet. Phát hiện hàng thiếu hoặc sai vị trí.
v1.0	Full Automation	Kiểm kê hàng ngày tự động hoàn toàn. Dashboard + alerts + auditing.


END OF DOCUMENT
VietJewelers © 2026 — Internal Use Only
