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


def anonymize_messages(messages, mapping):
    # Longest real name first, so e.g. "Trang Hoà Bình" is replaced before
    # a shorter unrelated match could interfere.
    compiled = [
        (re.compile(r"\b" + re.escape(real) + r"\b"), fake)
        for real, fake in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
    ]

    anonymized = []
    for item, raw_msg, source_file in messages:
        item = copy.deepcopy(item)
        text = item.get("text", "")
        if isinstance(text, str) and text:
            for pattern, fake in compiled:
                text = pattern.sub(fake, text)
            item["text"] = text
        anonymized.append((item, raw_msg, source_file))
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

    anonymized_messages = anonymize_messages(messages, mapping)

    OUT_RAW.parent.mkdir(exist_ok=True)
    with open(OUT_RAW, "w", encoding="utf-8") as f:
        json.dump([item for item, _, _ in anonymized_messages], f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(anonymized_messages)} anonymized raw messages (noise included) -> {OUT_RAW}")

    records, skipped = build_records(anonymized_messages)
    write_outputs(records, OUT_JSON, OUT_CSV, id_prefix="real_anon")
    print(f"Re-parsed {len(records)} transaction records from anonymized text -> {OUT_JSON.name} / {OUT_CSV.name}")


if __name__ == "__main__":
    main()
