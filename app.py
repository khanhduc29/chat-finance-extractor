import json
import math
from collections import defaultdict
from datetime import date, datetime
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

# Same palette reused to color chart segments by category
CATEGORY_COLORS = AVATAR_COLORS


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


def build_trend_and_cumulative(rows, width=880, height=220, pad_l=10, pad_r=10, pad_t=16, pad_b=28):
    daily = defaultdict(lambda: {"thu": 0, "chi": 0})
    for t in rows:
        if not t["date"] or not t["amount"]:
            continue
        if t["direction"] == "thu":
            daily[t["date"]]["thu"] += t["amount"]
        elif t["direction"] == "chi":
            daily[t["date"]]["chi"] += t["amount"]

    dates = sorted(daily)
    if not dates:
        return None, None

    series = []
    cum = 0
    for d in dates:
        thu, chi = daily[d]["thu"], daily[d]["chi"]
        net = thu - chi
        cum += net
        series.append({"date": d, "thu": thu, "chi": chi, "net": net, "cumulative": cum})

    n = len(series)
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def x_for(i):
        return pad_l + (i / (n - 1) if n > 1 else 0) * plot_w

    label_step = max(1, -(-n // 8))  # ~8 labels max, evenly spaced
    x_labels = [
        {"x": round(x_for(i), 1), "label": date.fromisoformat(s["date"]).strftime("%d/%m")}
        for i, s in enumerate(series)
        if i % label_step == 0 or i == n - 1
    ]

    trend_vals = [v for s in series for v in (s["thu"], s["chi"], s["net"])] + [0]
    t_min, t_max = min(trend_vals), max(trend_vals)
    t_span = (t_max - t_min) or 1

    def y_for_trend(v):
        return pad_t + (1 - (v - t_min) / t_span) * plot_h

    trend = {
        "width": width, "height": height,
        "zero_y": round(y_for_trend(0), 1),
        "thu_points": " ".join(f"{x_for(i):.1f},{y_for_trend(s['thu']):.1f}" for i, s in enumerate(series)),
        "chi_points": " ".join(f"{x_for(i):.1f},{y_for_trend(s['chi']):.1f}" for i, s in enumerate(series)),
        "net_points": " ".join(f"{x_for(i):.1f},{y_for_trend(s['net']):.1f}" for i, s in enumerate(series)),
        "x_labels": x_labels,
    }

    cum_vals = [s["cumulative"] for s in series] + [0]
    c_min, c_max = min(cum_vals), max(cum_vals)
    c_span = (c_max - c_min) or 1

    def y_for_cum(v):
        return pad_t + (1 - (v - c_min) / c_span) * plot_h

    line_pts = [(x_for(i), y_for_cum(s["cumulative"])) for i, s in enumerate(series)]
    zero_y_cum = round(y_for_cum(0), 1)
    area_pts = line_pts + [(x_for(n - 1), pad_t + plot_h), (x_for(0), pad_t + plot_h)]

    cumulative = {
        "width": width, "height": height,
        "zero_y": zero_y_cum,
        "line_points": " ".join(f"{x:.1f},{y:.1f}" for x, y in line_pts),
        "area_points": " ".join(f"{x:.1f},{y:.1f}" for x, y in area_pts),
        "x_labels": x_labels,
        "end_negative": series[-1]["cumulative"] < 0,
    }

    return trend, cumulative


def build_weekly_category_stack(rows, width=880, height=260, pad_l=10, pad_r=10, pad_t=16, pad_b=34):
    weeks = {}
    for t in rows:
        if not t["date"] or t["direction"] != "chi" or not t["amount"]:
            continue
        iso_year, iso_week, _ = date.fromisoformat(t["date"]).isocalendar()
        key = (iso_year, iso_week)
        wk = weeks.setdefault(key, {"label": f"Tuần {iso_week}", "cats": defaultdict(int)})
        wk["cats"][t["category_label"]] += t["amount"]

    week_keys = sorted(weeks)
    if not week_keys:
        return None

    totals = defaultdict(int)
    for k in week_keys:
        for cat, amt in weeks[k]["cats"].items():
            totals[cat] += amt
    cat_order = sorted(totals, key=lambda c: totals[c], reverse=True)
    cat_color = {cat: CATEGORY_COLORS[i % len(CATEGORY_COLORS)] for i, cat in enumerate(cat_order)}

    max_total = max(sum(weeks[k]["cats"].values()) for k in week_keys) or 1
    n = len(week_keys)
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bar_gap = 20
    bar_w = (plot_w - bar_gap * (n - 1)) / n

    bars = []
    for i, k in enumerate(week_keys):
        x = pad_l + i * (bar_w + bar_gap)
        y_cursor = pad_t + plot_h
        segments = []
        for cat in cat_order:
            amt = weeks[k]["cats"].get(cat, 0)
            if not amt:
                continue
            seg_h = amt / max_total * plot_h
            y_cursor -= seg_h
            segments.append({
                "y": round(y_cursor, 1), "h": round(seg_h, 1),
                "color": cat_color[cat], "cat": cat, "amt": amt,
            })
        bars.append({
            "x": round(x, 1), "w": round(bar_w, 1), "label": weeks[k]["label"],
            "segments": segments, "total": sum(weeks[k]["cats"].values()),
        })

    legend = [{"cat": cat, "color": cat_color[cat]} for cat in cat_order]

    return {
        "width": width, "height": height, "bars": bars, "legend": legend,
        "plot_bottom": round(pad_t + plot_h, 1),
    }


def build_category_donut(by_category, size=180, stroke=30):
    total = sum(c["thu"] + c["chi"] for c in by_category) or 1
    r = (size - stroke) / 2
    cx = cy = size / 2
    circumference = 2 * math.pi * r

    segments = []
    offset = 0
    for i, c in enumerate(by_category):
        val = c["thu"] + c["chi"]
        if not val:
            continue
        dash = val / total * circumference
        segments.append({
            "color": CATEGORY_COLORS[i % len(CATEGORY_COLORS)],
            "dash": round(dash, 2), "gap": round(circumference - dash, 2),
            "offset": round(-offset, 2),
            "label": c["label"], "value": val, "pct": round(val / total * 100, 1),
        })
        offset += dash

    return {
        "size": size, "r": r, "cx": cx, "cy": cy, "stroke": stroke,
        "segments": segments, "total": total,
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

    trend, cumulative = build_trend_and_cumulative(rows)
    weekly_stack = build_weekly_category_stack(rows)
    donut = build_category_donut(by_category)

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
        trend=trend,
        cumulative=cumulative,
        weekly_stack=weekly_stack,
        donut=donut,
        recent=recent,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
