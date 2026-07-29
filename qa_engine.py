"""
Shared Q&A logic for the "hỏi đáp nhanh" feature on the stats dashboard.

Builds a compact Vietnamese-text summary of the transaction data (not the
full 160 raw records, to keep the prompt small and cheap) and calls the
OpenAI Chat Completions API with it as grounding context, so a question
like "tháng này lãi hay lỗ" gets an answer based on the actual numbers
instead of a hallucinated one.

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
    'Bạn là trợ lý phân tích số liệu thu chi cho nhóm chat "Thu Chi - Công Ty". '
    "Chỉ trả lời dựa trên DỮ LIỆU TÓM TẮT được cung cấp bên dưới, không bịa số liệu "
    "ngoài đó. Nếu câu hỏi cần chi tiết không có trong tóm tắt (vd một giao dịch cụ "
    "thể không nằm trong danh sách), hãy nói rõ là không đủ dữ liệu để trả lời chính "
    "xác thay vì đoán. Trả lời ngắn gọn, rõ ràng, bằng tiếng Việt, dùng số liệu cụ "
    "thể kèm đơn vị VND khi phù hợp."
)


def build_qa_context(rows, top_n=10):
    total_thu = sum(t["amount"] for t in rows if t["direction"] == "thu" and t["amount"])
    total_chi = sum(t["amount"] for t in rows if t["direction"] == "chi" and t["amount"])
    dates = sorted({t["date"] for t in rows if t["date"]})
    flagged = sum(1 for t in rows if t["parse_warnings"])

    by_category = defaultdict(lambda: {"thu": 0, "chi": 0, "count": 0})
    by_employee = defaultdict(lambda: {"thu": 0, "chi": 0, "count": 0})
    by_bank = defaultdict(lambda: {"thu": 0, "chi": 0, "count": 0})

    for t in rows:
        amt = t["amount"] or 0
        direction = t["direction"]
        for bucket_map, bucket_key in (
            (by_category, t["category_label"]),
            (by_employee, t["sender_name"]),
            (by_bank, t.get("bank_code") or "?"),
        ):
            bucket = bucket_map[bucket_key]
            bucket["count"] += 1
            if direction == "thu":
                bucket["thu"] += amt
            elif direction == "chi":
                bucket["chi"] += amt

    top_transactions = sorted(
        (t for t in rows if t["amount"]), key=lambda t: t["amount"], reverse=True
    )[:top_n]

    lines = [
        f"Khoảng thời gian: {dates[0]} đến {dates[-1]}" if dates else "Không có ngày hợp lệ",
        f"Tổng số giao dịch: {len(rows)} (thiếu trường bắt buộc: {flagged})",
        f"Tổng thu: {total_thu:,} VND",
        f"Tổng chi: {total_chi:,} VND",
        f"Chênh lệch (net): {total_thu - total_chi:,} VND",
        "",
        "Theo loại giao dịch (category):",
    ]
    for cat, v in sorted(by_category.items(), key=lambda kv: kv[1]["thu"] + kv[1]["chi"], reverse=True):
        lines.append(f"- {cat}: thu {v['thu']:,} / chi {v['chi']:,} / {v['count']} giao dịch")

    lines.append("")
    lines.append("Theo nhân viên:")
    for emp, v in sorted(by_employee.items(), key=lambda kv: kv[1]["thu"] + kv[1]["chi"], reverse=True):
        lines.append(f"- {emp}: thu {v['thu']:,} / chi {v['chi']:,} / {v['count']} giao dịch")

    lines.append("")
    lines.append("Theo ngân hàng (bank_code):")
    for bank, v in sorted(by_bank.items(), key=lambda kv: kv[1]["thu"] + kv[1]["chi"], reverse=True):
        lines.append(f"- {bank}: thu {v['thu']:,} / chi {v['chi']:,} / {v['count']} giao dịch")

    lines.append("")
    lines.append(f"{top_n} giao dịch có số tiền lớn nhất:")
    for t in top_transactions:
        sign = "+" if t["direction"] == "thu" else "-"
        lines.append(
            f"- {t['date_display']} · {t['sender_name']} · {sign}{t['amount']:,} VND · "
            f"{t['category_label']} · {t['content']}"
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
