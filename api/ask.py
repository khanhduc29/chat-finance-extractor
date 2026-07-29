"""
Vercel Python Serverless Function backing the "hỏi đáp nhanh" panel on the
deployed static demo (docs/stats.html). Mirrors app.py's /api/ask Flask
route so the same frontend fetch('/api/ask') call works whether the page
is served by `python app.py` locally or by the Vercel deployment.

Vercel auto-detects any api/*.py file as a Serverless Function and routes
POST /api/ask here — no extra config needed. Requires the
real_transactions_anon.json data file (repo root) to be present in the
deployment, which it is by default.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa_engine import ask_openai, build_qa_context  # noqa: E402

TRANSACTIONS_FILE = Path(__file__).resolve().parent.parent / "real_transactions_anon.json"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            data = {}

        question = (data.get("question") or "").strip()
        if not question:
            self._send_json(400, {"error": "Thiếu câu hỏi"})
            return

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            self._send_json(500, {"error": "Server chưa cấu hình OPENAI_API_KEY"})
            return

        with open(TRANSACTIONS_FILE, encoding="utf-8") as f:
            rows = json.load(f)
        context = build_qa_context(rows)

        try:
            answer = ask_openai(question, context, api_key, model=os.environ.get("OPENAI_MODEL"))
        except Exception as e:
            self._send_json(502, {"error": str(e)})
            return

        self._send_json(200, {"answer": answer})

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
