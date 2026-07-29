"""
Bulk up the multi-group demo with more test volume:
  1. More messages appended to the 3 existing (real, anonymized) groups,
     continuing each group's own established style/format, with more days
     and more variety of transaction/task types than the first pass.
  2. Three brand-new, entirely fictional department groups (Phòng Nhân Sự,
     Phòng Marketing, Phòng Kho - Vận Chuyển) with their own distinct chat
     style, to exercise the multi-group interface with more variety.

This script is meant to be run ONCE against the real anonymized baseline
(data/anonymized_zalo_data.json right after anonymize_real_data.py, i.e.
165 messages, no synthetic bulk yet) — re-running it against its own
previous output would duplicate every message. If you need to regenerate,
reset the baseline first:
    git show <baseline-commit>:data/anonymized_zalo_data.json > data/anonymized_zalo_data.json

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
    "kho-van-chuyen": {"group_id": "TEST_GROUP_KHOVC_0001", "name": "Phòng Kho - Vận Chuyển"},
}

FAKE_CUSTOMERS = [
    "chị Lam Thái Nguyên", "anh Kiệt Vinh", "cô Nhàn Hải Phòng", "chú Bằng Nam Định",
    "chị Thắm Bắc Ninh", "anh Sang Hưng Yên", "chị Yên Ninh Bình", "anh Vĩ Thanh Hóa",
    "chị Diệu Quảng Ninh", "anh Phát Hải Dương", "cô Xuyến Vĩnh Phúc", "chú Đạt Phú Thọ",
    "chị Ngọc Bắc Giang", "anh Hoàng Thái Bình",
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


# Extra synthetic staff who also report thu-chi in these two groups —
# distinct from "NV Gia Bảo" (the real accountant, anonymized), so the
# synthetic portion of the data shows more than one name reporting.
HOP_DONG_STAFF = [
    ("syn_xuan", "NV Gia Bảo"), ("syn_nhung", "NV Hồng Nhung"), ("syn_quan2", "NV Minh Quân"),
]
TAI_CHINH_STAFF = [
    ("syn_xuan", "NV Gia Bảo"), ("syn_duong", "NV Thùy Dương"), ("syn_khoa", "NV Đăng Khoa"),
]


def gen_hop_dong_extra():
    group_id = EXISTING_GROUPS["hop-dong"]
    msgs = []
    invoice = 128
    for day_offset in range(6):
        day = datetime(2026, 7, 29) + timedelta(days=day_offset)
        for i in range(8):
            sid, name = random.choice(HOP_DONG_STAFF)
            customer = random.choice(FAKE_CUSTOMERS)
            amount = random.choice([500_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000, 4_500_000])
            action = random.choice(["cọc", "tất toán", "tất toán", "hoàn cọc"])
            sign = "-" if action == "hoàn cọc" else "+"
            text = (
                f"Ngày: {day.day:02d}/07/2026\n"
                f"Tk Xuân.svl.{sign} {amount:,} vnd\n"
                f"Nội dung: {action} HD{invoice}. {customer}"
            )
            msgs.append(make_message(group_id, sid, name, text, business_hour(day, i)))
            invoice += 1
    return msgs


def gen_tai_chinh_extra():
    group_id = EXISTING_GROUPS["tai-chinh"]
    msgs = []
    invoice = 130
    for day_offset in range(6):
        day = datetime(2026, 7, 29) + timedelta(days=day_offset)
        for i in range(7):
            sid, name = random.choice(TAI_CHINH_STAFF)
            kind = random.choice(["coc", "cash_advance", "office", "thu_no", "van_chuyen", "marketing"])
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
            elif kind == "office":
                amount = random.choice([300_000, 450_000, 600_000])
                text = (
                    f"Ngày: {day.day:02d}/07/2026\n"
                    f"Tk Xuân.svl. - {amount:,} vnd\n"
                    f"Nội dung: thanh toán tiền điện nước văn phòng"
                )
            elif kind == "thu_no":
                customer = random.choice(FAKE_CUSTOMERS)
                amount = random.choice([1_500_000, 2_000_000, 3_500_000])
                text = (
                    f"Ngày: {day.day:02d}/07/2026\n"
                    f"Tk Xuân.svl. + {amount:,} vnd\n"
                    f"Nội dung: thu công nợ HD{invoice}. {customer}"
                )
                invoice += 1
            elif kind == "van_chuyen":
                amount = random.choice([150_000, 280_000, 400_000])
                text = (
                    f"Ngày: {day.day:02d}/07/2026\n"
                    f"Tk tiền mặt Xuân.svl: - {amount:,}\n"
                    f"Nội dung: chi phí ship hàng cho khách"
                )
            else:
                amount = random.choice([500_000, 1_000_000, 1_800_000])
                text = (
                    f"Ngày: {day.day:02d}/07/2026\n"
                    f"Tk Xuân.svl. - {amount:,} vnd\n"
                    f"Nội dung: chạy ads quảng cáo Facebook"
                )
            msgs.append(make_message(group_id, sid, name, text, business_hour(day, i)))
    return msgs


KINH_DOANH_TASKS = [
    "tư vấn khách mới qua page", "chốt đơn khách quen", "gọi điện chăm sóc khách cũ",
    "gửi báo giá cho khách hỏi bàn ghế gỗ", "quay video sản phẩm mới", "up bài lên Zalo/Facebook",
    "kiểm tra tồn kho mẫu trưng bày", "hẹn khách xem hàng tại xưởng",
    "theo dõi đơn hàng đang giao", "xử lý khách hàng đổi trả", "báo giá dự án khách sạn mới",
    "tổng hợp doanh số tuần", "đào tạo sản phẩm mới cho nhân viên",
]


def gen_kinh_doanh_extra():
    group_id = EXISTING_GROUPS["kinh-doanh"]
    staff = [("syn_kd1", "NV Thảo My"), ("syn_kd2", "NV Quang Huy"), ("syn_kd3", "NV Hải Đăng")]
    msgs = []
    for day_offset in range(6):
        day = datetime(2026, 7, 29) + timedelta(days=day_offset)
        for i in range(6):
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
    "Thông báo lịch nghỉ lễ 2/9, công ty nghỉ 2 ngày, đi làm bù thứ 7 tuần trước đó",
    "Danh sách nhân viên thử việc sắp hết hạn tháng 8, các trưởng phòng đánh giá gửi em trước 5/8",
    "Nhắc mọi người nộp hóa đơn công tác phí tháng 7 trước cuối tuần để làm lương",
    "Bên bảo hiểm gọi xác nhận lại danh sách tham gia BHXH quý 3, ai thiếu thông tin báo em",
    "Tổ chức team building cuối quý, mọi người khảo sát địa điểm giúp em trong link",
]


def gen_nhan_su():
    group_id = NEW_GROUPS["nhan-su"]["group_id"]
    staff = [("syn_hr1", "NV Bích Ngọc"), ("syn_hr2", "NV Trọng Nghĩa"), ("syn_hr3", "NV Việt Hà")]
    msgs = []
    for day_offset in range(6):
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
    "Mẫu banner Trung Thu đã xong, gửi anh duyệt trước khi in standee",
    "Thống kê tuần này: fanpage tăng 340 follow mới, chủ yếu từ ads khu vực Hà Nội",
    "Có khách inbox hỏi giá sofa da thật, đã chuyển thông tin qua nhóm kinh doanh",
    "Chuẩn bị kịch bản livestream giới thiệu bộ sưu tập mới cuối tuần này",
    "Ngân sách ads tháng 8 đã duyệt, tăng 15% so với tháng 7 tập trung vào video",
]


def gen_marketing():
    group_id = NEW_GROUPS["marketing"]["group_id"]
    staff = [("syn_mk1", "NV Diễm My"), ("syn_mk2", "NV Anh Tuấn"), ("syn_mk3", "NV Bảo Trân")]
    msgs = []
    for day_offset in range(6):
        day = datetime(2026, 7, 28) + timedelta(days=day_offset)
        for i in range(5):
            sid, name = random.choice(staff)
            text = random.choice(MARKETING_MESSAGES)
            msgs.append(make_message(group_id, sid, name, text, business_hour(day, i)))
    return msgs


KHO_VC_MESSAGES = [
    "Kiểm kho sáng nay: còn 4 bộ sofa vải mã SF-102, 2 bộ da mã SF-205",
    "Đơn hàng HD125 đã đóng gói xong, chờ xe giao lúc 2h chiều",
    "Xe giao hàng khu vực quận 7 bị trễ do kẹt xe, báo khách dời sang chiều",
    "Nhập thêm 20 khung ghế gỗ từ xưởng, đã nhập kho xong",
    "Khách trả lại 1 bộ bàn ăn do lỗi vận chuyển, đang kiểm tra để đổi mới",
    "Chốt danh sách hàng xuất kho trong tuần, gửi phòng kinh doanh đối chiếu",
    "Kho nguyên liệu vải bọc sắp hết, cần đặt thêm trước cuối tháng",
    "Đã giao xong 5 đơn khu vực nội thành, còn 2 đơn ngoại thành hẹn mai",
    "Kiểm tra lại số lượng ghế trưng bày ở showroom, thiếu 1 cái so với sổ kho",
    "Đóng gói cẩn thận đơn hàng đi tỉnh xa, khách yêu cầu bọc thêm lớp chống ẩm",
    "Lịch giao hàng thứ 7 tuần này dồn nhiều đơn, cần thêm 1 xe tải hỗ trợ",
    "Đã nhận hàng trả về từ khách hủy đơn HD119, nhập lại kho",
]


def gen_kho_van_chuyen():
    group_id = NEW_GROUPS["kho-van-chuyen"]["group_id"]
    staff = [("syn_kho1", "NV Đức Thịnh"), ("syn_kho2", "NV Xuân Mai")]
    msgs = []
    for day_offset in range(6):
        day = datetime(2026, 7, 28) + timedelta(days=day_offset)
        for i in range(4):
            sid, name = random.choice(staff)
            text = random.choice(KHO_VC_MESSAGES)
            msgs.append(make_message(group_id, sid, name, text, business_hour(day, i)))
    return msgs


def main():
    with open(ANON_DATA_FILE, encoding="utf-8") as f:
        existing = json.load(f)

    new_messages = (
        gen_hop_dong_extra() + gen_tai_chinh_extra() + gen_kinh_doanh_extra()
        + gen_nhan_su() + gen_marketing() + gen_kho_van_chuyen()
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
