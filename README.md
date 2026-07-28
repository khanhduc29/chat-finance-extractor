# Zalo Thu Chi Parser

Bộ công cụ mô phỏng dữ liệu tin nhắn nhóm Zalo về thu chi doanh nghiệp, phân rã (parse)
nội dung tin nhắn tự do thành dữ liệu giao dịch có cấu trúc, và trực quan hoá lại dưới
dạng giao diện chat + dashboard thống kê.

## Cấu trúc dự án

```
.
├── zalo_thu_chi_data.json         # Dữ liệu tin nhắn thô (giả lập theo schema export Zalo)
├── extract_transactions.py        # Pipeline phân rã tin nhắn thô -> giao dịch có cấu trúc
├── transactions.json              # Kết quả phân rã (dùng cho app thống kê)
├── transactions.csv               # Kết quả phân rã, dạng CSV để mở bằng Excel/Sheets
├── app.py                         # Ứng dụng Flask: xem hội thoại + trang thống kê
├── templates/
│   ├── index.html                 # Giao diện chat mô phỏng Zalo
│   └── stats.html                 # Dashboard thống kê (theo loại/nhân viên/tài khoản/ngày)
├── Bao_cao_Phan_ra_Du_lieu_Thu_Chi.docx  # Báo cáo mô tả quy trình & cách phân rã
└── README.md
```

## Yêu cầu

- Python 3.10+
- Flask (`pip install flask`)
- python-docx nếu cần tạo lại báo cáo `.docx` (`pip install python-docx`)

## Cách chạy

1. (Tuỳ chọn) Tạo lại dữ liệu tin nhắn thô — script sinh dữ liệu nằm ngoài repo này,
   hoặc chỉnh sửa trực tiếp `zalo_thu_chi_data.json` nếu đã có sẵn.

2. Phân rã tin nhắn thô thành giao dịch có cấu trúc:

   ```bash
   python extract_transactions.py
   ```

   Lệnh này đọc `zalo_thu_chi_data.json` và ghi ra `transactions.json` +
   `transactions.csv`, kèm log tổng thu/chi và số giao dịch bị cảnh báo/thiếu trường.

3. Chạy ứng dụng xem dữ liệu:

   ```bash
   python app.py
   ```

   Mở trình duyệt tại:
   - `http://127.0.0.1:5000/` — giao diện chat mô phỏng Zalo
   - `http://127.0.0.1:5000/stats` — dashboard thống kê (tổng quan, giao dịch gần đây,
     theo loại giao dịch, theo nhân viên, theo tài khoản, theo ngày — bấm vào từng
     dòng để xem chi tiết)

## Quy trình phân rã (tóm tắt)

Mỗi tin nhắn có nội dung dạng:

```
Ngày: 27/07/2026
Tk Xuân.svl. - 400,000 vnd
Nội dung: thanh toán ship đệm a Đạt Hưng Yên về bảo hành
```

`extract_transactions.py` xử lý qua 5 bước:

1. **Tách trường cú pháp** — regex tách ngày / tài khoản + dấu +-/số tiền / nội dung.
2. **Chuẩn hoá tiếng Việt** — bỏ dấu để so khớp từ khóa không phân biệt dấu.
3. **Phân tích ngữ nghĩa** — tách câu "Nội dung" thành các slot: `action` (hành động),
   `objects` (đối tượng/vấn đề), `roles` (vai trò đối phương), `locations` (địa điểm),
   `time_period`, `counterparty` (tên người), `order_ref` (mã đơn).
4. **Suy ra loại giao dịch** — kết hợp các slot ngữ nghĩa ở trên với hướng thu/chi
   (dấu +/-) qua một danh sách luật ưu tiên, thay vì so khớp từ khóa toàn câu.
5. **Validate** — gắn cờ cảnh báo cho các bản ghi thiếu trường bắt buộc.

Chi tiết đầy đủ (gồm các lỗi thực tế gặp phải và cách sửa) xem trong
`Bao_cao_Phan_ra_Du_lieu_Thu_Chi.docx`.
