"""
Parse REAL Zalo group exports (data/raw/*.json) into the same normalized
transaction schema used by extract_transactions.py, but with a much more
tolerant field-extraction stage — real chat data is messier than the
synthetic demo data in several specific ways:

  1. Each message is duplicated once per pageId/psid the export mirrors it
     under (same rawMessage.msgId, multiple _id wrappers) -> dedupe by msgId.
  2. Most messages in a group are NOT thu-chi reports (system messages,
     photo/file shares, plain chat, proposals) -> only messages whose text
     contains a "Ngày: dd/mm/yyyy" line are treated as transaction candidates.
  3. The "Tk ..." line varies: "." or ":" before the sign, "tiền mặt" cash
     sub-ledger prefix (with or without a name after it), "vnd"/"vnđ" or no
     currency suffix at all, 1-2 digit day/month dates.
  4. A single message can report movements across more than one account
     (e.g. part bank transfer + part cash) -> each "Tk ..." line becomes its
     own transaction record sharing the same message_id.
  5. Order refs use "HD123"/"DH123" (invoice/order code), not "#1234".

Semantic analysis (action/objects/roles/locations/category) is reused as-is
from extract_transactions.py — it's the same lexicon-driven logic, just fed
real "Nội dung" text instead of synthetic templates.
"""
import csv
import json
import re
from pathlib import Path

from extract_transactions import CATEGORY_LABELS, analyze_semantics

RAW_DIR = Path(__file__).parent / "data" / "raw"
OUT_JSON = Path(__file__).parent / "real_transactions.json"
OUT_CSV = Path(__file__).parent / "real_transactions.csv"

DATE_RE = re.compile(r"Ngày:\s*(\d{1,2})/(\d{1,2})/(\d{4})")
CONTENT_RE = re.compile(r"Nội dung:\s*(.+)", re.DOTALL)
ORDER_RE = re.compile(r"\b(HD|DH)\s*[-.]?\s*(\d+)", re.IGNORECASE)

# One match per "Tk <label>[.:][+-]<amount>[vnd/vnđ]" occurrence in the
# header (before "Nội dung:") — a message can contain more than one.
TK_LINE_RE = re.compile(
    r"\bTk\s+(?P<label>.+?)\s*[.:]\s*(?P<sign>[+-])\s*(?P<amount>[\d.,]+)\s*(?:vn[dđ])?",
    re.IGNORECASE,
)


def parse_date(match):
    d, m, y = match.group(1), match.group(2), match.group(3)
    return f"{y}-{int(m):02d}-{int(d):02d}", f"{int(d):02d}/{int(m):02d}/{y}"


def parse_account_label(label):
    """Split a raw "Tk" label into (account_type, holder, bank_code).

    Examples:
      "Xuân.svl"          -> bank, "Xuân", "svl"
      "Xuân"              -> bank, "Xuân", None
      "tiền mặt Xuân.svl" -> cash, "Xuân", "svl"
      "tiền mặt Xuân"     -> cash, "Xuân", None
      "tiền mặt"          -> cash, None, None
    """
    label = label.strip()
    account_type = "bank"
    if re.match(r"tiền\s*mặt", label, re.IGNORECASE):
        account_type = "cash"
        label = re.sub(r"^tiền\s*mặt\s*", "", label, flags=re.IGNORECASE).strip()

    if not label:
        return account_type, None, None
    if "." in label:
        holder, bank_code = label.rsplit(".", 1)
        return account_type, holder.strip() or None, bank_code.strip().lower() or None
    return account_type, label, None


def load_raw_messages():
    seen_msg_ids = set()
    messages = []
    for path in sorted(RAW_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        for item in items:
            text = item.get("text", "")
            if not isinstance(text, str) or not text:
                continue
            raw_msg = item.get("rawMessage") or {}
            msg_id = raw_msg.get("msgId")
            if not msg_id or msg_id in seen_msg_ids:
                continue
            seen_msg_ids.add(msg_id)
            messages.append((item, raw_msg, path.name))
    return messages


def build_records(messages):
    records = []
    skipped_non_transaction = 0

    for item, raw_msg, source_file in messages:
        text = item["text"]
        date_m = DATE_RE.search(text)
        if not date_m:
            skipped_non_transaction += 1
            continue

        date_iso, date_display = parse_date(date_m)
        content_m = CONTENT_RE.search(text)
        content = content_m.group(1).strip() if content_m else ""

        header = text[: content_m.start()] if content_m else text
        tk_matches = list(TK_LINE_RE.finditer(header))
        primary_direction = (
            ("thu" if tk_matches[0].group("sign") == "+" else "chi") if tk_matches else None
        )

        warnings = []
        if not content_m:
            warnings.append("missing_content")

        semantics = (
            analyze_semantics(content, primary_direction)
            if content
            else {
                "action": None, "objects": [], "roles": [], "locations": [],
                "time_period": None, "order_ref": None, "person": None,
                "category": "khac", "category_label": CATEGORY_LABELS["khac"],
            }
        )
        order_m = ORDER_RE.search(content)
        order_ref = f"{order_m.group(1).upper()}{order_m.group(2)}" if order_m else None

        base = {
            "message_id": raw_msg.get("msgId"),
            "source_file": source_file,
            "sender_name": raw_msg.get("dName"),
            "date": date_iso,
            "date_display": date_display,
            "timestamp": item.get("timestamp", {}).get("$date"),
            "currency": "VND",
            "content": content,
            "action": semantics["action"],
            "objects": semantics["objects"],
            "roles": semantics["roles"],
            "locations": semantics["locations"],
            "time_period": semantics["time_period"],
            "counterparty": semantics["person"],
            "order_ref": order_ref,
            "category": semantics["category"],
            "category_label": semantics["category_label"],
        }

        if not tk_matches:
            rec = dict(base)
            rec.update({
                "line_index": 0,
                "account_type": None, "account_holder": None, "bank_code": None,
                "direction": None, "amount": None,
                "parse_warnings": warnings + ["missing_amount_or_account"],
            })
            records.append(rec)
            continue

        for i, m in enumerate(tk_matches):
            account_type, holder, bank_code = parse_account_label(m.group("label"))
            amount = int(m.group("amount").replace(",", "").replace(".", ""))
            direction = "thu" if m.group("sign") == "+" else "chi"
            rec = dict(base)
            rec.update({
                "line_index": i,
                "account_type": account_type,
                "account_holder": holder,
                "bank_code": bank_code,
                "direction": direction,
                "amount": amount,
                "parse_warnings": list(warnings),
            })
            records.append(rec)

    return records, skipped_non_transaction


def write_outputs(records, out_json, out_csv, id_prefix="real"):
    for i, rec in enumerate(records, start=1):
        rec["transaction_id"] = f"{id_prefix}_{i:05d}"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "transaction_id", "message_id", "source_file", "date", "sender_name",
        "account_type", "account_holder", "bank_code", "direction", "amount",
        "currency", "category_label", "action", "objects", "roles", "locations",
        "time_period", "counterparty", "order_ref", "content", "parse_warnings",
    ]
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = dict(r)
            row["objects"] = ";".join(r["objects"])
            row["roles"] = ";".join(r["roles"])
            row["locations"] = ";".join(r["locations"])
            row["parse_warnings"] = ";".join(r["parse_warnings"])
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main():
    messages = load_raw_messages()
    records, skipped = build_records(messages)
    write_outputs(records, OUT_JSON, OUT_CSV)

    total_thu = sum(r["amount"] for r in records if r["direction"] == "thu" and r["amount"])
    total_chi = sum(r["amount"] for r in records if r["direction"] == "chi" and r["amount"])
    flagged = [r for r in records if r["parse_warnings"]]
    uncategorized = [r for r in records if r["category"] == "khac"]
    multi_line_msgs = len({r["message_id"] for r in records if r["line_index"] > 0})

    print(f"Loaded {len(messages)} unique raw messages (across {len(list(RAW_DIR.glob('*.json')))} files)")
    print(f"Skipped as non-transaction chat: {skipped}")
    print(f"Parsed {len(records)} transaction records")
    print(f"  - messages with >1 account line: {multi_line_msgs}")
    print(f"Total thu: {total_thu:,} VND")
    print(f"Total chi: {total_chi:,} VND")
    print(f"Net: {total_thu - total_chi:,} VND")
    print(f"Records with parse warnings: {len(flagged)}")
    print(f"Uncategorized (category=khac): {len(uncategorized)}")


if __name__ == "__main__":
    main()
