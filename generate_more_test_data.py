"""
Bulk up the multi-group demo with more test volume:
  1. More messages appended to the 3 existing (real, anonymized) groups,
     continuing each group's own established style/format.
  2. Two brand-new, entirely fictional department groups (Phòng Nhân Sự,
     Phòng Marketing) with their own distinct chat style, to exercise the
     multi-group interface with more variety.

Everything generated here is synthetic from the start — no real customer/
staff data involved, so none of it needs to go through anonymize_real_data.py.
Output is appended directly onto data/anonymized_zalo_data.json (the file
app.py actually reads), and real_transactions_anon.json/csv is regenerated
from the combined set so the stats page picks up the new hop-dong/tai-chinh
transactions too.
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from extract_real_transactions import build_records, write_outputs

random.seed(42)

ANON_DATA_FILE = Path(__file__).parent / "data" / "anonymized_zalo_data.json"
OUT_JSON = Path(__file__).parent / "real_transactions_anon.json"
OUT_CSV = Path(__file__).parent / "real_transactions_anon.csv"

EXISTING_GROUPS = {
    "hop-dong": "JJ5J3QDPI9087EQVSI1544U43F03SIG0",
    "tai-chinh": "SJ29PSLKI578TDMAT66A0D6M9QR45QO0",
    "kinh-doanh": "5KARD73PGN446UUL4HFL4P07GEHQL8G0",
}
NEW_GROUPS = {
    "nhan-su": {"group_id": "TEST_GROUP_NHAN_SU_0001", "name": "Phòng Nhân Sự"},
    "marketing": {"group_id": "TEST_GROUP_MARKETING_0001", "name": "Phòng Marketing"},
}

FAKE_CUSTOMERS = [
    "chị Lam Thái Nguyên", "anh Kiệt Vinh", "cô Nhàn Hải Phòng", "chú Bằng Nam Định",
    "chị Thắm Bắc Ninh", "anh Sang Hưng Yên", "chị Yên Ninh Bình", "anh Vĩ Thanh Hóa",
]

_msg_counter = 0


def next_msg_id(prefix):
    global _msg_counter
    _msg_counter += 1
    return f"synthetic_{prefix}_{_msg_counter:05d}"


def make_message(group_id, sender_id, dname, text, dt):
    return {
        "_id": next_msg_id(group_id[:6].lower()),
        "globalGroupId": group_id,
        "psid": f"g{group_id[:16]}",
        "senderId": sender_id,
        "rawMessage": {"msgId": next_msg_id(group_id[:6].lower()), "dName": dname},
        "text": text,
        "timestamp": {"$date": dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"},
    }


def business_hour(day, i):
    return day.replace(hour=8, minute=0, second=0) + timedelta(minutes=15 * i)


def gen_hop_dong_extra():
    group_id = EXISTING_GROUPS["hop-dong"]
    msgs = []
    invoice = 128
    for day_offset in range(3):
        day = datetime(2026, 7, 29) + timedelta(days=day_offset)
        for i in range(7):
            customer = random.choice(FAKE_CUSTOMERS)
            amount = random.choice([500_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000])
            sign = "+"
            action = random.choice(["cọc", "tất toán"])
            text = (
                f"Ngày: {day.day:02d}/07/2026\n"
                f"Tk Xuân.svl.{sign} {amount:,} vnd\n"
                f"Nội dung: {action} HD{invoice}. {customer}"
            )
            msgs.append(make_message(group_id, "syn_xuan", "NV Gia Bảo", text, business_hour(day, i)))
            invoice += 1
    return msgs


def gen_tai_chinh_extra():
    group_id = EXISTING_GROUPS["tai-chinh"]
    msgs = []
    invoice = 130
    for day_offset in range(3):
        day = datetime(2026, 7, 29) + timedelta(days=day_offset)
        for i in range(6):
            kind = random.choice(["coc", "cash_advance", "office"])
            if kind == "coc":
                customer = random.choice(FAKE_CUSTOMERS)
                amount = random.choice([800_000, 1_200_000, 2_500_000])
                text = (
                    f"Ngày: {day.day:02d}/07/2026\n"
                    f"Tk Tiền mặt Xuân.svl: + {amount:,} vnđ\n"
                    f"Nội dung: cọc HD{invoice}. {customer}"
                )
                invoice += 1
            elif kind == "cash_advance":
                amount = random.choice([1_000_000, 2_000_000, 3_000_000])
                text = (
                    f"Ngày: {day.day:02d}/07/2026\n"
                    f"Tk tiền mặt Xuân.svl:- {amount:,}\n"
                    f"Nội dung: tạm ứng lương tháng 7"
                )
            else:
                amount = random.choice([300_000, 450_000, 600_000])
                text = (
                    f"Ngày: {day.day:02d}/07/2026\n"
                    f"Tk Xuân.svl. - {amount:,} vnd\n"
                    f"Nội dung: thanh toán tiền điện nước văn phòng"
                )
            msgs.append(make_message(group_id, "syn_xuan", "NV Gia Bảo", text, business_hour(day, i)))
    return msgs


KINH_DOANH_TASKS = [
    "tư vấn khách mới qua page", "chốt đơn khách quen", "gọi điện chăm sóc khách cũ",
    "gửi báo giá cho khách hỏi bàn ghế gỗ", "quay video sản phẩm mới", "up bài lên Zalo/Facebook",
    "kiểm tra tồn kho mẫu trưng bày", "hẹn khách xem hàng tại xưởng",
]


def gen_kinh_doanh_extra():
    group_id = EXISTING_GROUPS["kinh-doanh"]
    staff = [("syn_kd1", "NV Thảo My"), ("syn_kd2", "NV Quang Huy")]
    msgs = []
    for day_offset in range(3):
        day = datetime(2026, 7, 29) + timedelta(days=day_offset)
        for i in range(5):
            sid, name = random.choice(staff)
            tasks = random.sample(KINH_DOANH_TASKS, k=3)
            text = f"{day.day}/7/2026: " + "; ".join(tasks)
            msgs.append(make_message(group_id, sid, name, text, business_hour(day, i)))
    return msgs


NHAN_SU_MESSAGES = [
    "Anh/chị cho em xin nghỉ phép ngày mai vì việc gia đình ạ",
    "Nhắc cả nhà chấm công đầy đủ trước 9h sáng nhé",
    "Ứng viên phỏng vấn vị trí kế toán hẹn 14h chiều mai, ai rảnh vào cùng phỏng vấn với em",
    "Đã gửi bảng lương tháng 7 cho các phòng, mọi người kiểm tra giúp em nếu có sai sót báo lại",
    "Công ty tổ chức khám sức khỏe định kỳ vào thứ 7 tuần sau, đăng ký với em trước thứ 5",
    "Bạn Long bên kho xin nghỉ ốm 2 ngày, đã duyệt",
    "Nhắc lại quy định chấm công: đi muộn quá 15 phút tính nửa buổi nhé mọi người",
    "Tuyển thêm 1 bạn nhân viên giao hàng, mọi người giới thiệu giúp em với",
    "Sinh nhật bạn Hằng phòng kinh doanh hôm nay, mọi người qua chúc mừng nhé",
    "Đã cập nhật nội quy công ty bản mới, gửi vào nhóm để mọi người đọc",
]


def gen_nhan_su():
    group_id = NEW_GROUPS["nhan-su"]["group_id"]
    staff = [("syn_hr1", "NV Bích Ngọc"), ("syn_hr2", "NV Trọng Nghĩa")]
    msgs = []
    for day_offset in range(4):
        day = datetime(2026, 7, 28) + timedelta(days=day_offset)
        for i in range(5):
            sid, name = random.choice(staff)
            text = random.choice(NHAN_SU_MESSAGES)
            msgs.append(make_message(group_id, sid, name, text, business_hour(day, i)))
    return msgs


MARKETING_MESSAGES = [
    "Tuần này lên lịch 5 bài đăng Facebook, 2 video TikTok cho dòng sofa mới",
    "Ảnh sản phẩm mới chụp xong chưa, gửi anh duyệt trước 5h chiều nay",
    "Chỉ số tương tác bài hôm qua tăng 20% so với tuần trước, chạy tiếp ngân sách cho bài đó",
    "Đề xuất chạy thêm ads cho khu vực Hà Nội + Sài Gòn tuần sau",
    "Video review khách hàng vừa quay xong, đang dựng, mai có bản nháp",
    "Landing page mới đã lên, mọi người test giúp trên điện thoại xem load ổn không",
    "Đối thủ vừa ra mẫu sofa mới, mọi người xem qua để mình có hướng làm nội dung so sánh",
    "Đã gửi content calendar tháng 8 vào nhóm, mọi người xem góp ý giúp em",
    "Booking KOL review sản phẩm tuần sau, đang chờ báo giá",
    "Bài viết blog về cách chọn sofa phòng khách nhỏ lên top tìm kiếm rồi mọi người",
]


def gen_marketing():
    group_id = NEW_GROUPS["marketing"]["group_id"]
    staff = [("syn_mk1", "NV Diễm My"), ("syn_mk2", "NV Anh Tuấn")]
    msgs = []
    for day_offset in range(4):
        day = datetime(2026, 7, 28) + timedelta(days=day_offset)
        for i in range(5):
            sid, name = random.choice(staff)
            text = random.choice(MARKETING_MESSAGES)
            msgs.append(make_message(group_id, sid, name, text, business_hour(day, i)))
    return msgs


def main():
    with open(ANON_DATA_FILE, encoding="utf-8") as f:
        existing = json.load(f)

    new_messages = (
        gen_hop_dong_extra() + gen_tai_chinh_extra() + gen_kinh_doanh_extra()
        + gen_nhan_su() + gen_marketing()
    )
    print(f"Existing messages: {len(existing)}")
    print(f"New synthetic messages: {len(new_messages)}")

    combined = existing + new_messages
    with open(ANON_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(combined)} total messages -> {ANON_DATA_FILE}")

    # Rebuild transaction records from the combined set (only hop-dong /
    # tai-chinh messages contain "Tk ... amount" lines; the rest are noise).
    tuples = [(item, item.get("rawMessage") or {}, "combined") for item in combined]
    records, skipped = build_records(tuples)
    write_outputs(records, OUT_JSON, OUT_CSV, id_prefix="real_anon")
    print(f"Re-parsed {len(records)} transaction records (skipped {skipped} non-transaction) -> {OUT_JSON.name}")


if __name__ == "__main__":
    main()
