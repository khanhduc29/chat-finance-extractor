import json
from datetime import datetime
from html import escape
from pathlib import Path

from flask import Flask, render_template
from markupsafe import Markup

app = Flask(__name__)

DATA_FILE = Path(__file__).parent / "zalo_thu_chi_data.json"
TRANSACTIONS_FILE = Path(__file__).parent / "transactions.json"
GROUP_NAME = "Thu Chi - Công Ty"

# Consistent color per sender, cycled from a fixed palette
AVATAR_COLORS = [
    "#3477eb", "#e0554f", "#2ea86f", "#e0a72e", "#8657d6",
    "#d64f8f", "#3fb0c9", "#c97a3f", "#6f7ce0", "#4fae4f",
    "#2f9e8f", "#b85c9e",
]


def format_bubble_html(text):
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        escaped = escape(line)
        if line.strip().startswith("Tk "):
            css_class = "tag-thu" if "+" in line else "tag-chi" if "-" in line else ""
            if css_class:
                escaped = f'<span class="{css_class}">{escaped}</span>'
        html_lines.append(escaped)
    return Markup("<br>".join(html_lines))


def load_messages():
    with open(DATA_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    messages = []
    for item in raw:
        raw_msg = item["rawMessage"]
        dt = datetime.strptime(item["timestamp"]["$date"], "%Y-%m-%dT%H:%M:%S.%fZ")
        messages.append({
            "sender_id": item["senderId"],
            "name": raw_msg["dName"],
            "text": format_bubble_html(item["text"]),
            "dt": dt,
            "time": dt.strftime("%H:%M"),
            "date_key": dt.strftime("%Y-%m-%d"),
            "date_label": dt.strftime("%d/%m/%Y"),
        })

    messages.sort(key=lambda m: m["dt"])

    # assign a stable color per sender
    sender_ids = []
    for m in messages:
        if m["sender_id"] not in sender_ids:
            sender_ids.append(m["sender_id"])
    color_map = {sid: AVATAR_COLORS[i % len(AVATAR_COLORS)] for i, sid in enumerate(sender_ids)}
    for m in messages:
        m["color"] = color_map[m["sender_id"]]
        m["initial"] = m["name"].strip()[-1].upper() if m["name"].strip() else "?"

    # group consecutive messages by date, and mark first message of a run from same sender
    grouped = []
    current_date = None
    prev_sender = None
    for m in messages:
        if m["date_key"] != current_date:
            grouped.append({"type": "date", "label": m["date_label"]})
            current_date = m["date_key"]
            prev_sender = None
        m["show_header"] = (m["sender_id"] != prev_sender)
        grouped.append({"type": "message", **m})
        prev_sender = m["sender_id"]

    return grouped, len(messages), len(sender_ids)


def load_transactions():
    with open(TRANSACTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def display_tx(t):
    return {
        **t,
        "amount_fmt": f"{t['amount']:,}" if t["amount"] else "-",
        "direction_label": "Thu" if t["direction"] == "thu" else "Chi",
    }


def aggregate(rows, key_fn, label_fn=None, collect_items=False):
    buckets = {}
    for t in rows:
        key = key_fn(t)
        if key is None:
            continue
        label = label_fn(t) if label_fn else key
        b = buckets.setdefault(key, {
            "key": key, "label": label, "thu": 0, "chi": 0, "count": 0,
            "transactions": [] if collect_items else None,
        })
        b["count"] += 1
        if t["direction"] == "thu" and t["amount"]:
            b["thu"] += t["amount"]
        elif t["direction"] == "chi" and t["amount"]:
            b["chi"] += t["amount"]
        if collect_items:
            b["transactions"].append(display_tx(t))
    result = list(buckets.values())
    result.sort(key=lambda b: b["thu"] + b["chi"], reverse=True)
    if collect_items:
        for b in result:
            b["transactions"].sort(key=lambda t: t["timestamp"], reverse=True)
    return result


@app.route("/")
def index():
    items, total, member_count = load_messages()
    return render_template(
        "index.html",
        items=items,
        group_name=GROUP_NAME,
        total=total,
        member_count=member_count,
    )


@app.route("/stats")
def stats():
    rows = load_transactions()

    total_thu = sum(t["amount"] for t in rows if t["direction"] == "thu" and t["amount"])
    total_chi = sum(t["amount"] for t in rows if t["direction"] == "chi" and t["amount"])
    flagged = [t for t in rows if t["parse_warnings"]]

    by_category = aggregate(rows, lambda t: t["category"], lambda t: t["category_label"])
    by_employee = aggregate(rows, lambda t: t["sender_name"], collect_items=True)
    by_account = aggregate(rows, lambda t: t["account"], collect_items=True)
    by_date = aggregate(rows, lambda t: t["date"], lambda t: t["date_display"], collect_items=True)
    by_date.sort(key=lambda b: b["key"], reverse=True)

    recent = sorted(rows, key=lambda t: t["timestamp"], reverse=True)[:15]
    recent = [display_tx(t) for t in recent]

    return render_template(
        "stats.html",
        group_name=GROUP_NAME,
        total_count=len(rows),
        total_thu=total_thu,
        total_chi=total_chi,
        net=total_thu - total_chi,
        flagged_count=len(flagged),
        by_category=by_category,
        by_employee=by_employee,
        by_account=by_account,
        by_date=by_date,
        recent=recent,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
