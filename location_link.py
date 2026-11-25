#!/usr/bin/env python3
"""
location_link.py — Consent-based location sharing link system.

Standard library only (http.server). No Flask, no third-party packages.

How it works:
  1. The owner creates a one-purpose link:  GET /new?key=<ADMIN_KEY>
  2. The owner sends the /l/<token> link to someone (e.g. a family member).
  3. The page honestly explains — in Bengali and English — that tapping the
     button will share THEIR OWN location with the person who sent the link.
     Nothing is captured before the tap. There is a Cancel option.
  4. If (and only if) the visitor taps "Share my location" and the browser's
     own permission prompt is approved, the browser sends {lat, lon,
     accuracy} to /api/loc/<token>. The result is appended to locations.jsonl
     and, if configured, forwarded to the owner on Telegram.

Configuration (environment variables):
  PORT              Port to listen on            (default 8090)
  ADMIN_KEY         Required to create links. If unset, link creation is
                    disabled (the /new endpoint answers with a clear error).
  LINK_TTL_HOURS    Link lifetime in hours       (default 24)
  LOC_BOT_TOKEN     Telegram bot token           (optional)
  LOC_OWNER_CHAT_ID Telegram chat id of owner    (optional)
                    If the Telegram variables are unset, locations are only
                    written to locations.jsonl — the server never crashes
                    because of a missing/failed Telegram call.

Endpoints:
  GET  /new?key=<ADMIN_KEY>   -> JSON {token, url, expires_at}
  GET  /l/<token>             -> consent page (or friendly error page)
  POST /api/loc/<token>       -> JSON {ok: true}
  GET  /health                -> 200 "ok"

Data files (next to this script): tokens.json, locations.jsonl
"""

import json
import os
import secrets
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENS_FILE = os.path.join(BASE_DIR, "tokens.json")
LOCATIONS_FILE = os.path.join(BASE_DIR, "locations.jsonl")

PORT = int(os.environ.get("PORT", "8090"))
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
LINK_TTL_HOURS = float(os.environ.get("LINK_TTL_HOURS", "24"))
BOT_TOKEN = os.environ.get("LOC_BOT_TOKEN", "")
OWNER_CHAT_ID = os.environ.get("LOC_OWNER_CHAT_ID", "")

_tokens_lock = threading.Lock()


# --------------------------------------------------------------------------
# Token storage
# --------------------------------------------------------------------------

def load_tokens() -> dict:
    try:
        with open(TOKENS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_tokens(tokens: dict) -> None:
    tmp = TOKENS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(tokens, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, TOKENS_FILE)  # atomic


def create_token() -> dict:
    token = secrets.token_urlsafe(16)
    expires = datetime.now(timezone.utc) + timedelta(hours=LINK_TTL_HOURS)
    with _tokens_lock:
        tokens = load_tokens()
        tokens[token] = {"created_at": datetime.now(timezone.utc).isoformat(),
                         "expires_at": expires.isoformat()}
        save_tokens(tokens)
    return {"token": token, "url": f"/l/{token}", "expires_at": expires.isoformat()}


def token_status(token: str) -> str:
    """Return 'ok', 'unknown' or 'expired'."""
    with _tokens_lock:
        tokens = load_tokens()
    entry = tokens.get(token)
    if not entry:
        return "unknown"
    try:
        expires = datetime.fromisoformat(entry["expires_at"])
    except (KeyError, ValueError):
        return "unknown"
    if datetime.now(timezone.utc) > expires:
        return "expired"
    return "ok"


# --------------------------------------------------------------------------
# Telegram notification (optional, failure-proof)
# --------------------------------------------------------------------------

def notify_telegram(lat, lon, accuracy) -> None:
    if not BOT_TOKEN or not OWNER_CHAT_ID:
        return
    now = datetime.now().astimezone().strftime("%Y-%m-%d %I:%M %p")
    acc = f"~{accuracy:.0f}m" if isinstance(accuracy, (int, float)) else "unknown"
    text = ("📍 নতুন লোকেশন পাওয়া গেছে\n"
            f"সময়: {now}\n"
            f"Google Maps: https://www.google.com/maps?q={lat},{lon}\n"
            f"Accuracy: {acc}")
    payload = json.dumps({"chat_id": OWNER_CHAT_ID, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as exc:  # never let Telegram failure break the server
        print(f"[warn] Telegram notify failed: {exc}", flush=True)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

CONSENT_PAGE = """<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>লোকেশন শেয়ার করুন / Share your location</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 24px; background: #f6f7f9; color: #1c1e21; }
  .card { max-width: 480px; margin: 40px auto; background: #fff; border-radius: 14px;
          padding: 28px 22px; box-shadow: 0 2px 12px rgba(0,0,0,.08); text-align: center; }
  h1 { font-size: 22px; margin: 0 0 12px; }
  p { font-size: 16px; line-height: 1.55; }
  .en { color: #555; font-size: 14px; }
  button { display: block; width: 100%; border: 0; border-radius: 10px; cursor: pointer;
           padding: 16px; font-size: 19px; margin-top: 18px; }
  #share { background: #1a9e54; color: #fff; }
  #cancel { background: #e8eaed; color: #333; }
  #msg { margin-top: 18px; font-size: 16px; min-height: 24px; }
</style>
</head>
<body>
<div class="card">
  <h1>📍 লোকেশন শেয়ার করুন</h1>
  <p>যিনি আপনাকে এই লিংকটি পাঠিয়েছেন, তিনি আপনার বর্তমান লোকেশনটি দেখতে চান।
     নিচের বোতামে চাপ দিলে আপনার ফোনের লোকেশন শুধুমাত্র তাঁর কাছেই পাঠানো হবে।</p>
  <p class="en">The person who sent you this link is asking for your current
     location. Tap the button below to share YOUR location with them — and only
     with them. Nothing is sent unless you tap the button and approve your
     browser's permission prompt.</p>
  <button id="share">📍 আমার লোকেশন শেয়ার করুন / Share my location</button>
  <button id="cancel">বাতিল / Cancel</button>
  <div id="msg"></div>
</div>
<script>
  var msg = document.getElementById('msg');
  document.getElementById('cancel').addEventListener('click', function () {
    msg.textContent = 'বাতিল করা হয়েছে। কোনো লোকেশন পাঠানো হয়নি। / Cancelled — no location was sent.';
  });
  document.getElementById('share').addEventListener('click', function () {
    if (!navigator.geolocation) {
      msg.textContent = 'এই ব্রাউজারে লোকেশন সুবিধা নেই। / Geolocation is not supported by this browser.';
      return;
    }
    msg.textContent = 'লোকেশন নেওয়া হচ্ছে… / Getting your location…';
    navigator.geolocation.getCurrentPosition(function (pos) {
      fetch('/api/loc/__TOKEN__', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy
        })
      }).then(function (r) {
        if (r.ok) {
          msg.textContent = '✅ ধন্যবাদ! আপনার লোকেশন পাঠানো হয়েছে। / Thank you! Your location has been shared.';
        } else {
          msg.textContent = 'দুঃখিত, পাঠানো যায়নি। লিংকটির মেয়াদ শেষ হয়ে থাকতে পারে। / Sorry, it could not be sent. The link may have expired.';
        }
      }).catch(function () {
        msg.textContent = 'দুঃখিত, পাঠানো যায়নি। আবার চেষ্টা করুন। / Sorry, sending failed. Please try again.';
      });
    }, function (err) {
      msg.textContent = 'লোকেশন পাওয়া যায়নি। অনুমতি দেওয়া হয়নি বা GPS বন্ধ আছে। / Location unavailable — permission denied or GPS is off.';
    }, { enableHighAccuracy: true, timeout: 20000 });
  });
</script>
</body>
</html>
"""

ERROR_PAGE = """<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>লিংকটি কাজ করছে না / Link not working</title>
<style>
  body { font-family: sans-serif; margin: 0; padding: 24px; background: #f6f7f9; color: #1c1e21; }
  .card { max-width: 480px; margin: 40px auto; background: #fff; border-radius: 14px;
          padding: 28px 22px; box-shadow: 0 2px 12px rgba(0,0,0,.08); text-align: center; }
  p { font-size: 16px; line-height: 1.55; }
  .en { color: #555; font-size: 14px; }
</style>
</head>
<body>
<div class="card">
  <p>⚠️ __MESSAGE_BN__</p>
  <p class="en">__MESSAGE_EN__</p>
</div>
</body>
</html>
"""


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "LocationLink/1.0"

    # -- helpers -----------------------------------------------------------
    def _send(self, code, body, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _error_page(self, code, bn, en):
        html = ERROR_PAGE.replace("__MESSAGE_BN__", bn).replace("__MESSAGE_EN__", en)
        self._send(code, html)

    # -- routes ------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send(200, "ok", "text/plain; charset=utf-8")
            return

        if path == "/new":
            if not ADMIN_KEY:
                self._send_json(403, {"ok": False,
                                      "error": "Link creation is disabled: ADMIN_KEY is not set on the server."})
                return
            key = parse_qs(parsed.query).get("key", [""])[0]
            if key != ADMIN_KEY:
                self._send_json(403, {"ok": False, "error": "Invalid admin key."})
                return
            self._send_json(200, create_token())
            return

        if path.startswith("/l/"):
            token = path[3:].strip("/")
            status = token_status(token)
            if status == "ok":
                self._send(200, CONSENT_PAGE.replace("__TOKEN__", token))
            elif status == "expired":
                self._error_page(410, "এই লিংকটির মেয়াদ শেষ হয়ে গেছে। যিনি পাঠিয়েছেন, তাঁর কাছ থেকে নতুন লিংক চান।",
                                 "This link has expired. Please ask the sender for a new link.")
            else:
                self._error_page(404, "এই লিংকটি পাওয়া যায়নি। লিংকটি ঠিকমতো কপি হয়েছে কিনা দেখুন।",
                                 "This link was not found. Please check that the link was copied correctly.")
            return

        self._send_json(404, {"ok": False, "error": "Not found."})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/loc/"):
            token = path[len("/api/loc/"):].strip("/")
            status = token_status(token)
            if status != "ok":
                self._send_json(410 if status == "expired" else 404,
                                {"ok": False, "error": f"Link {status}."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 64 * 1024:
                self._send_json(400, {"ok": False, "error": "Bad request body."})
                return
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                lat = float(data["lat"])
                lon = float(data["lon"])
                accuracy = data.get("accuracy")
                accuracy = float(accuracy) if accuracy is not None else None
            except (ValueError, KeyError, TypeError):
                self._send_json(400, {"ok": False, "error": "Expected JSON with numeric lat and lon."})
                return

            entry = {
                "time": datetime.now(timezone.utc).isoformat(),
                "token": token,
                "lat": lat,
                "lon": lon,
                "accuracy": accuracy,
                "ip": self.client_address[0],
                "user_agent": self.headers.get("User-Agent", ""),
            }
            with _tokens_lock:
                with open(LOCATIONS_FILE, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            notify_telegram(lat, lon, accuracy)
            self._send_json(200, {"ok": True})
            return

        self._send_json(404, {"ok": False, "error": "Not found."})


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"location_link server listening on 0.0.0.0:{PORT}", flush=True)
    print(f"  link creation: {'enabled' if ADMIN_KEY else 'DISABLED (ADMIN_KEY not set)'}",
          flush=True)
    print(f"  telegram notify: {'enabled' if (BOT_TOKEN and OWNER_CHAT_ID) else 'off (logging to locations.jsonl only)'}",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
