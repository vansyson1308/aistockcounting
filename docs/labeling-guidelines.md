# Labeling Guidelines (VietJewelers - class `item`)

## 1) Định nghĩa 1 "item"
- Chỉ có **1 class** duy nhất: `item`.
- Mỗi món trang sức vật lý nhìn thấy được đếm là 1 item.
- **Earrings policy:** mỗi chiếc bông tai là 1 item (một đôi = 2 item).

## 2) Quy tắc vẽ bounding box
- Box phải **tight**: bao sát biên vật thể, không dư nền quá mức.
- Không cắt mất vùng chính của vật thể.
- Cho phép chồng box nếu vật thể chồng lấn.
- Nếu bị che khuất (occlusion), vẫn gán box cho phần nhìn thấy được.

## 3) Edge cases
- **Rings touching:** 2 nhẫn chạm nhau vẫn là 2 box riêng nếu phân biệt được.
- **Chains overlapping:** mỗi sợi dây là 1 box nếu tách được; nếu dính không tách nổi thì 1 box bao cụm và note QA.
- **Earrings pair:** một đôi = 2 box.
- **Reflections/mirror:** không label ảnh phản chiếu giả, chỉ label vật thật.
- **Partial out-of-frame:** vật thể bị cắt khung vẫn label phần nhìn thấy.
- **Blur:** nếu vẫn nhận diện được vật thể thì label; mờ nặng không xác định thì bỏ qua và cờ QA.

## 4) Do / Don't checklist
### Do
- Zoom trước khi label chi tiết.
- Giữ quy tắc nhất quán giữa các ảnh.
- Ghi chú bất thường (khó tách vật thể).

### Don't
- Không vẽ box quá rộng lấy nhiều nền.
- Không label reflection như vật thật.
- Không thay đổi class name (`item` là duy nhất).

## 5) QA rubric
- **Rejectable**
  - Sai class id.
  - Box lệch hoàn toàn khỏi vật thể.
  - Thiếu nhiều vật thể rõ ràng.
  - Box cực nhỏ/degenerate do lỗi thao tác.
- **Acceptable**
  - Sai khác nhỏ vài pixel ở biên.
  - Occlusion khó nhưng đã bao phần nhìn thấy hợp lý.

## 6) Convention metadata
- File ảnh nên giữ ổn định theo format: `<record_id>_<tray_id>.jpg` (nếu có tray_id).
- Manifest phải có: `record_id, tray_id, staff_id, created_at, image_filename`.
- Không đổi tên file sau khi bắt đầu labeling task để tránh lệch annotation.
