"""
Shared Q&A logic for the "hỏi đáp nhanh" feature on the stats dashboard.

Builds a text context for the OpenAI Chat Completions API entirely from the
FIELDS ALREADY PARSED by extract_transactions.py (category, action, objects,
roles, locations, time_period, counterparty, account_holder, bank_code, ...)
rather than asking the model to re-interpret the raw "content" free text
itself — the parsing pipeline already did that work and is the source of
truth. Two parts: (1) an aggregate summary (by category/employee/bank/role/
object/location) for quick macro questions, and (2) the full chronological
list of every transaction with its parsed fields as tags, so date-specific,
week-specific, order-specific, or "nhân viên X vào ngày Y" style questions
can be computed exactly instead of getting a "không đủ dữ liệu" refusal.
The dataset is small (~160 rows), so shipping the full list is cheap.

Used by both app.py (Flask route /api/ask, for `python app.py` locally)
and api/ask.py (Vercel serverless function, for the deployed static demo)
so there is exactly one place that owns the context format and the
OpenAI call.
"""
import json
import urllib.error
import urllib.request
from collections import defaultdict

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "Bạn là trợ lý phân tích số liệu thu chi tổng hợp từ các nhóm chat Zalo báo cáo "
    "thu chi của công ty (tên khách hàng đã được ẩn danh). "
    "Dữ liệu bên dưới đến từ một pipeline đã PHÂN RÃ sẵn từng tin nhắn thành các "
    "trường có cấu trúc: category (loại giao dịch), action (hành động), objects "
    "(đối tượng/khoản mục), roles (vai trò đối phương), locations (địa điểm), "
    "time_period, counterparty (tên người), order_ref (mã đơn), account_holder/"
    "bank_code (tài khoản). PHẢI DÙNG CÁC TRƯỜNG ĐÃ PHÂN RÃ NÀY làm căn cứ chính "
    "để trả lời (vd hỏi 'chi cho khách hàng' → dùng roles=khach_hang; hỏi 'chi phí "
    "ở Hưng Yên' → dùng locations; hỏi 'khách nào còn nợ' → dùng category=Công nợ + "
    "counterparty), thay vì tự suy diễn lại từ câu chữ thô trong 'nội dung' — phần "
    "nội dung chỉ để tham khảo ngữ cảnh thêm khi các trường phân rã không đủ rõ. "
    "Dùng danh sách đầy đủ giao dịch (phần 2) để tự tính tổng/so sánh cho bất kỳ "
    "ngày, khoảng ngày, tuần, nhân viên, ngân hàng, hay mã đơn hàng cụ thể nào được "
    "hỏi. Chỉ trả lời dựa trên dữ liệu được cung cấp, không bịa số liệu ngoài đó — "
    "nếu thực sự không có trong dữ liệu thì nói rõ thay vì đoán. Trả lời ngắn gọn, "
    "rõ ràng, bằng tiếng Việt, có số liệu cụ thể kèm đơn vị VND khi phù hợp."
)


def _aggregate_by(rows, key_fn, multi=False):
    """key_fn returns either one key (multi=False) or a list of keys (multi=True)
    a single transaction can belong to (objects/roles/locations are lists)."""
    buckets = defaultdict(lambda: {"thu": 0, "chi": 0, "count": 0})
    for t in rows:
        amt = t["amount"] or 0
        direction = t["direction"]
        keys = key_fn(t) if multi else [key_fn(t)]
        for key in keys:
            if not key:
                continue
            bucket = buckets[key]
            bucket["count"] += 1
            if direction == "thu":
                bucket["thu"] += amt
            elif direction == "chi":
                bucket["chi"] += amt
    return buckets


def _render_bucket(lines, title, buckets):
    lines.append("")
    lines.append(title)
    for key, v in sorted(buckets.items(), key=lambda kv: kv[1]["thu"] + kv[1]["chi"], reverse=True):
        lines.append(f"- {key}: thu {v['thu']:,} / chi {v['chi']:,} / {v['count']} giao dịch")


def build_qa_context(rows):
    total_thu = sum(t["amount"] for t in rows if t["direction"] == "thu" and t["amount"])
    total_chi = sum(t["amount"] for t in rows if t["direction"] == "chi" and t["amount"])
    dates = sorted({t["date"] for t in rows if t["date"]})
    flagged = sum(1 for t in rows if t["parse_warnings"])

    lines = [
        f"Khoảng thời gian: {dates[0]} đến {dates[-1]}" if dates else "Không có ngày hợp lệ",
        f"Tổng số giao dịch: {len(rows)} (thiếu trường bắt buộc: {flagged})",
        f"Tổng thu: {total_thu:,} VND",
        f"Tổng chi: {total_chi:,} VND",
        f"Chênh lệch (net): {total_thu - total_chi:,} VND",
    ]

    _render_bucket(lines, "Theo loại giao dịch (category):", _aggregate_by(rows, lambda t: t["category_label"]))
    _render_bucket(lines, "Theo nhân viên:", _aggregate_by(rows, lambda t: t["sender_name"]))
    _render_bucket(lines, "Theo ngân hàng (bank_code):", _aggregate_by(rows, lambda t: (t.get("bank_code") or "?").upper()))
    _render_bucket(lines, "Theo vai trò đối phương (roles):", _aggregate_by(rows, lambda t: t["roles"], multi=True))
    _render_bucket(lines, "Theo đối tượng/khoản mục (objects):", _aggregate_by(rows, lambda t: t["objects"], multi=True))
    _render_bucket(lines, "Theo địa điểm (locations):", _aggregate_by(rows, lambda t: t["locations"], multi=True))

    lines.append("")
    lines.append(f"Danh sách đầy đủ {len(rows)} giao dịch, mỗi dòng kèm các trường đã phân rã (theo thứ tự thời gian):")
    for t in sorted(rows, key=lambda t: t["timestamp"]):
        sign = "+" if t["direction"] == "thu" else "-"
        amount = f"{t['amount']:,}" if t["amount"] else "?"
        bank = (
            f"{t.get('account_holder')}·{(t.get('bank_code') or '').upper()}"
            if t.get("bank_code") else t.get("account") or "?"
        )

        tags = []
        if t.get("action"):
            tags.append(f"action={t['action']}")
        if t.get("objects"):
            tags.append("objects=" + ",".join(t["objects"]))
        if t.get("roles"):
            tags.append("roles=" + ",".join(t["roles"]))
        if t.get("locations"):
            tags.append("dia_diem=" + ",".join(t["locations"]))
        if t.get("time_period"):
            tags.append(f"thoi_gian={t['time_period']}")
        if t.get("counterparty"):
            tags.append(f"doi_tac={t['counterparty']}")
        if t.get("order_ref"):
            tags.append(f"don_hang=#{t['order_ref']}")
        tag_str = f" [{' '.join(tags)}]" if tags else ""

        lines.append(
            f"- {t['date_display']} · {t['sender_name']} · TK {bank} · {sign}{amount} VND · "
            f"{t['category_label']}{tag_str} · nội dung: {t['content']}"
        )

    return "\n".join(lines)


def ask_openai(question, context, api_key, model=None, timeout=30):
    payload = {
        "model": model or DEFAULT_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\nDỮ LIỆU TÓM TẮT:\n" + context},
            {"role": "user", "content": question},
        ],
    }
    req = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API lỗi {e.code}: {detail[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Không kết nối được OpenAI API: {e.reason}") from e

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Phản hồi OpenAI không đúng định dạng: {data}")
