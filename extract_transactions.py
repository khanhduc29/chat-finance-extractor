"""
Parse raw Zalo group-chat export (zalo_thu_chi_data.json) into a normalized
transaction schema (transactions.json / transactions.csv) for statistics
and lookup.

Pipeline:
  1. Field extraction   - regex over the semi-structured "text" field
                           (Ngày / Tk .. +-amount / Nội dung)
  2. Normalization       - amount -> int, date -> ISO
  3. Semantic analysis   - decompose "Nội dung" (free text) into slots:
                           action (verb), objects (what it's about),
                           roles (who the counterparty is), locations,
                           time_period, order_ref, person name
  4. Category derivation - combine the slots above with priority rules
                           (not a flat keyword scan over the whole sentence)
  5. Validation          - flag records missing required fields
"""
import csv
import json
import re
import unicodedata
from pathlib import Path

SRC = Path(__file__).parent / "zalo_thu_chi_data.json"
OUT_JSON = Path(__file__).parent / "transactions.json"
OUT_CSV = Path(__file__).parent / "transactions.csv"

DATE_RE = re.compile(r"Ngày:\s*(\d{2}/\d{2}/\d{4})")
ACCOUNT_RE = re.compile(r"Tk\s+(.+?)\.\s*([+-])\s*([\d.,]+)\s*vnd", re.IGNORECASE)
CONTENT_RE = re.compile(r"Nội dung:\s*(.+)")
ORDER_RE = re.compile(r"#(\d+)")
TIME_PERIOD_RE = re.compile(r"tháng\s*\d{1,2}", re.IGNORECASE)
COUNTERPARTY_MARKERS = {"anh", "chị", "khách", "a", "c"}


def extract_counterparty(content):
    # Token-based on purpose: a single regex char-class spanning Vietnamese
    # accented letters (e.g. [A-ZÀ-Ỵ]) mixes precomposed code points from
    # blocks that interleave upper/lowercase, so it silently matches
    # lowercase words too (e.g. "đệm"). Checking str.isupper() per token
    # avoids that trap. Marker must be its own token, not a substring
    # (e.g. "mua" must not match the "a" marker).
    tokens = content.split()
    for i, tok in enumerate(tokens):
        if tok.lower() not in COUNTERPARTY_MARKERS:
            continue
        words = []
        for t in tokens[i + 1:]:
            stripped = t.strip(".,#")
            if stripped[:1].isupper():
                words.append(stripped)
            else:
                break
        if words:
            return " ".join(words)
    return None


def strip_accents(s):
    # "đ"/"Đ" are atomic Vietnamese letters, not base+combining-mark
    # sequences, so plain NFKD stripping leaves them untouched. Fold them
    # to "d" explicitly before removing the rest of the diacritics.
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    ).lower()


# --- Semantic lexicons -------------------------------------------------
# Each maps a canonical slot value to the surface phrases (accent-stripped)
# that signal it. Checked in order, longest/most-specific phrases first
# within each list, so "tạm ứng" doesn't get miscaught by a bare "ứng".

ACTION_LEXICON = [
    ("hoan_ung", ["hoan ung"]),
    ("ung", ["tam ung", "ung truoc", "ung tien", "ung luong"]),
    ("thu_hoi", ["thu hoi"]),
    ("dat_coc", ["dat coc"]),
    ("thanh_toan", ["thanh toan"]),
    ("chuyen", ["chuyen khoan", "chuyen quy"]),
    ("tiep_khach", ["tiep khach"]),
    ("do_xang", ["do xang"]),
    ("mua", ["mua"]),
    ("thu", ["thu tien", "thu lai"]),
    ("chi", ["chi tra", "chi luong", "chi thuong", "chi phi"]),
]

OBJECT_LEXICON = {
    "ship": ["ship", "van chuyen", "cuoc", " cod"],
    "luong": ["luong"],
    "cong_tac": ["cong tac"],
    "cong_no": ["cong no"],
    "vat_tu": ["vat tu"],
    "sua_chua": ["sua chua", "sua xe", "bao hanh"],
    "dien_nuoc": ["dien nuoc"],
    "van_phong_pham": ["van phong pham"],
    "thue_kho": ["thue kho"],
    "xang": ["xang"],
    "quang_cao": ["quang cao"],
    "hoa_hong": ["hoa hong"],
    "quy": ["quy tien mat"],
    "thuong": ["thuong doanh so", "tien thuong"],
    "phat": ["tien phat"],
    "hang_hoa": ["mua hang", "tra tien hang"],
    "don_hang": ["don hang", "dat coc"],
    "tam_ung_du": ["tam ung du"],
}

ROLE_LEXICON = {
    "khach_hang": ["khach si", "khach le", "khach"],
    "nha_cung_cap": ["nha cung cap", "xuong go", "dai ly"],
    "nhan_vien": ["nhan vien"],
    "doi_tac": ["doi tac"],
    "noi_bo": ["ke toan"],
}

LOCATION_LEXICON = [
    ("hung yen", "Hưng Yên"),
    ("hai phong", "Hải Phòng"),
    ("binh duong", "Bình Dương"),
    ("ha noi", "Hà Nội"),
    ("sai gon", "Sài Gòn"),
    ("ninh hiep", "Ninh Hiệp"),
    ("nam dinh", "Nam Định"),
]

# Category derivation rules: (predicate over slots) -> category key.
# Order matters - first matching rule wins. This replaces a flat keyword
# scan with a decision built on top of already-extracted semantic slots
# (action/object/role) PLUS the syntactic thu/chi direction from the "Tk"
# line, so e.g. a "chi" transaction that merely mentions "khách" in
# passing (mua hàng hộ khách) doesn't get miscategorized as customer
# revenue, while a "đặt cọc"/"thanh toán" that comes in as "thu" does.
CATEGORY_RULES = [
    (lambda a, o, r, d: "cong_no" in o, "cong_no"),
    (lambda a, o, r, d: a == "hoan_ung" or "cong_tac" in o, "tam_ung_cong_tac"),
    (lambda a, o, r, d: "luong" in o, "luong_ung_luong"),
    (lambda a, o, r, d: "thuong" in o or "phat" in o, "thuong_phat"),
    (lambda a, o, r, d: "ship" in o, "ship_van_chuyen"),
    (lambda a, o, r, d: a == "dat_coc" or "khach_hang" in r or (d == "thu" and a == "thanh_toan"), "khach_hang"),
    (lambda a, o, r, d: "vat_tu" in o or "sua_chua" in o, "vat_tu_sua_chua"),
    (lambda a, o, r, d: bool({"dien_nuoc", "van_phong_pham", "thue_kho", "xang"} & set(o)), "van_phong"),
    (lambda a, o, r, d: "quang_cao" in o or "hoa_hong" in o, "marketing"),
    (lambda a, o, r, d: "nha_cung_cap" in r or "hang_hoa" in o, "nha_cung_cap"),
    (lambda a, o, r, d: a == "tiep_khach", "tiep_khach"),
    (lambda a, o, r, d: "quy" in o or "tam_ung_du" in o, "noi_bo"),
]

CATEGORY_LABELS = {
    "cong_no": "Công nợ",
    "tam_ung_cong_tac": "Tạm ứng công tác",
    "luong_ung_luong": "Lương/Ứng lương",
    "thuong_phat": "Thưởng/Phạt",
    "ship_van_chuyen": "Ship/Vận chuyển",
    "khach_hang": "Khách hàng thanh toán",
    "vat_tu_sua_chua": "Vật tư/Sửa chữa",
    "van_phong": "Chi phí văn phòng",
    "marketing": "Marketing/Quảng cáo",
    "nha_cung_cap": "Nhà cung cấp",
    "tiep_khach": "Tiếp khách/Đối ngoại",
    "noi_bo": "Quỹ nội bộ",
    "khac": "Khác",
}


def analyze_semantics(content, direction=None):
    normalized = strip_accents(content)

    action = None
    for act, phrases in ACTION_LEXICON:
        if any(p in normalized for p in phrases):
            action = act
            break

    objects = [key for key, phrases in OBJECT_LEXICON.items() if any(p in normalized for p in phrases)]
    roles = [key for key, phrases in ROLE_LEXICON.items() if any(p in normalized for p in phrases)]
    locations = [label for key, label in LOCATION_LEXICON if key in normalized]

    time_m = TIME_PERIOD_RE.search(content)
    order_m = ORDER_RE.search(content)
    person = extract_counterparty(content)

    category = "khac"
    for predicate, cat_key in CATEGORY_RULES:
        if predicate(action, objects, roles, direction):
            category = cat_key
            break

    return {
        "action": action,
        "objects": objects,
        "roles": roles,
        "locations": locations,
        "time_period": time_m.group(0) if time_m else None,
        "order_ref": order_m.group(1) if order_m else None,
        "person": person,
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, category),
    }


def parse_message(item):
    text = item.get("text", "")
    raw_msg = item["rawMessage"]
    warnings = []

    date_m = DATE_RE.search(text)
    account_m = ACCOUNT_RE.search(text)
    content_m = CONTENT_RE.search(text)

    if not date_m:
        warnings.append("missing_date")
    if not account_m:
        warnings.append("missing_amount_or_account")
    if not content_m:
        warnings.append("missing_content")

    date_str = date_m.group(1) if date_m else None
    date_iso = None
    if date_str:
        d, mth, y = date_str.split("/")
        date_iso = f"{y}-{mth}-{d}"

    account = account_m.group(1).strip() if account_m else None
    account_holder, bank_code = account.rsplit(".", 1) if account and "." in account else (account, None)
    sign = account_m.group(2) if account_m else None
    amount_raw = account_m.group(3) if account_m else None
    amount = int(amount_raw.replace(",", "").replace(".", "")) if amount_raw else None
    direction = ("thu" if sign == "+" else "chi") if sign else None

    content = content_m.group(1).strip() if content_m else ""
    semantics = analyze_semantics(content, direction) if content else {
        "action": None, "objects": [], "roles": [], "locations": [],
        "time_period": None, "order_ref": None, "person": None,
        "category": "khac", "category_label": CATEGORY_LABELS["khac"],
    }

    record = {
        "transaction_id": None,  # filled below with running index
        "message_id": raw_msg["msgId"],
        "group_psid": item["psid"],
        "sender_uid": raw_msg["uidFrom"],
        "sender_name": raw_msg["dName"],
        "date": date_iso,
        "date_display": date_str,
        "timestamp": item["timestamp"]["$date"],
        "account": account,
        "account_holder": account_holder,
        "bank_code": bank_code,
        "direction": direction,
        "amount": amount,
        "currency": "VND",
        "content": content,
        "action": semantics["action"],
        "objects": semantics["objects"],
        "roles": semantics["roles"],
        "locations": semantics["locations"],
        "time_period": semantics["time_period"],
        "counterparty": semantics["person"],
        "order_ref": semantics["order_ref"],
        "category": semantics["category"],
        "category_label": semantics["category_label"],
        "parse_warnings": warnings,
    }
    return record


def main():
    with open(SRC, encoding="utf-8") as f:
        raw_messages = json.load(f)

    transactions = []
    for i, item in enumerate(raw_messages, start=1):
        rec = parse_message(item)
        rec["transaction_id"] = f"txn_{i:05d}"
        transactions.append(rec)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(transactions, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "transaction_id", "message_id", "date", "sender_name", "account",
        "account_holder", "bank_code",
        "direction", "amount", "currency", "category_label", "action",
        "objects", "roles", "locations", "time_period", "counterparty",
        "order_ref", "content",
    ]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in transactions:
            row = dict(t)
            row["objects"] = ";".join(t["objects"])
            row["roles"] = ";".join(t["roles"])
            row["locations"] = ";".join(t["locations"])
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    total_thu = sum(t["amount"] for t in transactions if t["direction"] == "thu" and t["amount"])
    total_chi = sum(t["amount"] for t in transactions if t["direction"] == "chi" and t["amount"])
    flagged = [t for t in transactions if t["parse_warnings"]]
    uncategorized = [t for t in transactions if t["category"] == "khac"]

    print(f"Parsed {len(transactions)} transactions")
    print(f"Total thu: {total_thu:,} VND")
    print(f"Total chi: {total_chi:,} VND")
    print(f"Net: {total_thu - total_chi:,} VND")
    print(f"Records with parse warnings: {len(flagged)}")
    print(f"Uncategorized (category=khac): {len(uncategorized)}")


if __name__ == "__main__":
    main()
