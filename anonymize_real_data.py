"""
Produce an anonymized copy of the real Zalo data for testing: every real
customer name found in a transaction message's "Nội dung" is replaced with
a fake name (consistently — the same real name always maps to the same
fake name), while ALL messages are kept, including the non-transaction
"noise" (system messages, chit-chat, photo/file shares, proposals) — so the
result is a realistic-shaped, safe-to-share dataset for exercising the chat
view and the parser, not just the clean transaction subset.

Only the top-level `text` field (the one both app.py's chat view and
extract_real_transactions.py actually read) is rewritten; nested
quote/rawMessage copies are left as-is.

Outputs:
  - data/anonymized_zalo_data.json   (all unique raw messages, noise included)
  - real_transactions_anon.json/.csv (re-parsed from the anonymized text)
"""
import copy
import itertools
import json
import re
from pathlib import Path

from extract_transactions import extract_counterparty
from extract_real_transactions import (
    CONTENT_RE,
    DATE_RE,
    build_records,
    load_raw_messages,
    write_outputs,
)

SYNTHETIC_TRANSACTIONS = Path(__file__).parent / "transactions.json"
OUT_RAW = Path(__file__).parent / "data" / "anonymized_zalo_data.json"
OUT_JSON = Path(__file__).parent / "real_transactions_anon.json"
OUT_CSV = Path(__file__).parent / "real_transactions_anon.csv"

# Extra fake customer names (same "tên + địa danh/mô tả" style as the
# existing demo data) to top up the pool — the synthetic dataset alone only
# has ~12 distinct counterparties, fewer than the real data's ~27.
SUPPLEMENTARY_FAKE_NAMES = [
    "Vân", "Bảo Ngọc", "Quỳnh Chi Nam Định", "Hà Thái Bình", "Trung Vĩnh Phúc",
    "Loan Quảng Ninh", "Duyên Hải Dương", "Bích Hà Nam", "Sơn Bắc Giang",
    "Huệ Thanh Hóa", "Khánh Vĩnh Yên", "Oanh Phú Thọ", "Giang Móng Cái",
    "Linh Đông Anh", "Phượng Gia Lâm", "Quân Cầu Giấy", "Hằng Sóc Sơn",
    "Diệp Từ Sơn", "Uyên Việt Trì", "Khoa Bỉm Sơn",
]

# Employee/staff display names (rawMessage.dName) get their own fake pool,
# separate from customers — "Smv <tên>" is the company's internal staff-tag
# prefix (Smv = Sao Mộc Vương), which itself leaks the real company name,
# so it's stripped along with the person's name, not just replaced 1:1.
STAFF_FAKE_NAMES = [
    "NV Minh Anh", "NV Gia Bảo", "NV Thu Hà", "NV Đức Huy", "NV Ngọc Lan",
    "NV Bảo Long", "NV Thùy Linh", "NV Hải Nam", "NV Anh Quân", "NV Thanh Tú",
]

# Real brand/company names that show up inside message content itself (not
# just in dName) — replaced with made-up brand names of the same kind
# (furniture/sofa business), so the anonymized data still reads naturally.
BRAND_MAPPING = {
    "Sao Mộc Vương": "Ánh Dương Group",
    "Savisofa": "Vinasofa",
    "Savilux": "Nội Thất An Khang",
    "SMVCons": "ADVCons",
    "smvcons": "advcons",
    "SMV": "ADV",
}


def collect_real_names(messages):
    names = []
    seen = set()
    for item, raw_msg, source_file in messages:
        text = item.get("text", "")
        if not isinstance(text, str) or not DATE_RE.search(text):
            continue
        content_m = CONTENT_RE.search(text)
        if not content_m:
            continue
        name = extract_counterparty(content_m.group(1).strip())
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def build_name_mapping(real_names):
    base_pool = []
    if SYNTHETIC_TRANSACTIONS.exists():
        synthetic = json.load(open(SYNTHETIC_TRANSACTIONS, encoding="utf-8"))
        base_pool = sorted({r["counterparty"] for r in synthetic if r.get("counterparty")})

    real_set = set(real_names)
    pool = [n for n in base_pool + SUPPLEMENTARY_FAKE_NAMES if n not in real_set]
    # de-dupe while preserving order
    pool = list(dict.fromkeys(pool))

    mapping = {}
    pool_cycle = itertools.cycle(pool)
    for real_name in sorted(real_names, key=len, reverse=True):
        mapping[real_name] = next(pool_cycle)
    return mapping


def collect_staff_dnames(messages):
    """Every distinct employee/page display name seen anywhere — not just in
    transaction-shaped messages, since staff also chat in the "noise"."""
    names = []
    seen = set()
    for item, raw_msg, source_file in messages:
        candidates = [raw_msg.get("dName")]
        frm = item.get("from") or {}
        candidates += [frm.get("displayName"), frm.get("zaloName"), frm.get("name")]
        for name in candidates:
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def build_staff_mapping(staff_names):
    pool = list(dict.fromkeys(STAFF_FAKE_NAMES))
    mapping = {}
    pool_cycle = itertools.cycle(pool)
    for name in sorted(staff_names, key=len, reverse=True):
        mapping[name] = next(pool_cycle)
    return mapping


def anonymize_messages(messages, customer_mapping, staff_mapping):
    # Longest name first everywhere, so e.g. "Kim Oanh Mộc Chất Smv Group"
    # is replaced before a shorter unrelated match (like bare "Smv") could
    # interfere with it.
    text_mapping = {**customer_mapping, **staff_mapping, **BRAND_MAPPING}
    compiled = [
        (re.compile(r"\b" + re.escape(real) + r"\b"), fake)
        for real, fake in sorted(text_mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
    ]

    anonymized = []
    for item, raw_msg, source_file in messages:
        item = copy.deepcopy(item)
        text = item.get("text", "")
        if isinstance(text, str) and text:
            for pattern, fake in compiled:
                text = pattern.sub(fake, text)
            item["text"] = text

        rm = item.get("rawMessage")
        if isinstance(rm, dict) and rm.get("dName") in staff_mapping:
            rm["dName"] = staff_mapping[rm["dName"]]
        frm = item.get("from")
        if isinstance(frm, dict):
            for key in ("displayName", "zaloName", "name"):
                if frm.get(key) in staff_mapping:
                    frm[key] = staff_mapping[frm[key]]

        # Re-fetch from the mutated item — `raw_msg` above is the stale
        # pre-anonymization reference captured by the caller's tuple.
        anonymized.append((item, item.get("rawMessage") or {}, source_file))
    return anonymized


def main():
    messages = load_raw_messages()

    real_names = collect_real_names(messages)
    mapping = build_name_mapping(real_names)
    print(f"Found {len(real_names)} distinct real customer names to anonymize")
    for real, fake in sorted(mapping.items())[:5]:
        print(f"  {real!r} -> {fake!r}")
    if len(mapping) > 5:
        print(f"  ... and {len(mapping) - 5} more")

    staff_names = collect_staff_dnames(messages)
    staff_mapping = build_staff_mapping(staff_names)
    print(f"\nFound {len(staff_names)} distinct staff/page display names to anonymize")
    for real, fake in staff_mapping.items():
        print(f"  {real!r} -> {fake!r}")
    print(f"\nBrand terms replaced: {list(BRAND_MAPPING.keys())}")

    anonymized_messages = anonymize_messages(messages, mapping, staff_mapping)

    OUT_RAW.parent.mkdir(exist_ok=True)
    with open(OUT_RAW, "w", encoding="utf-8") as f:
        json.dump([item for item, _, _ in anonymized_messages], f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(anonymized_messages)} anonymized raw messages (noise included) -> {OUT_RAW}")

    records, skipped = build_records(anonymized_messages)
    write_outputs(records, OUT_JSON, OUT_CSV, id_prefix="real_anon")
    print(f"Re-parsed {len(records)} transaction records from anonymized text -> {OUT_JSON.name} / {OUT_CSV.name}")


if __name__ == "__main__":
    main()
