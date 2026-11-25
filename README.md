# Number Tools (Bangladesh)

Two small, standalone Python tools. All code here is original; the only
external dependency is the well-known open-source **`phonenumbers`** library
(Google's libphonenumber port) used by Tool 1. Tool 2 uses nothing but the
Python standard library.

---

## Tool 1 — `number_info.py` · phone number info lookup

**What it does.** Given a Bangladeshi phone number, it prints a tidy report:

- E.164 / international / national formatting
- Whether the number is *possible* and *valid* (libphonenumber rules)
- Number type: mobile, fixed line (landline), VoIP, etc.
- Country/region and timezone(s)
- Area description from the libphonenumber geocoder
- **Carrier**, detected two ways:
  1. an explicit Bangladesh prefix map (primary source — BTRC allocation):
     013/017 Grameenphone · 014/019 Banglalink · 018 Robi ·
     016 Airtel (Robi) · 015 Teletalk · 011 Citycell (defunct)
  2. the library's own carrier lookup (secondary cross-check)

**Setup**

```bash
pip install phonenumbers
# — or, on systems with an externally-managed Python, use the bundled venv:
#   ~/workspace/number-tools/.venv/bin/python number_info.py 01712345678
```

**Run**

```bash
python3 number_info.py 01712345678
python3 number_info.py 01712345678 01912345678 +8801712345678 02-9123456
python3 number_info.py            # interactive: one number per line
```

Accepted formats: `01XXXXXXXXX`, `8801XXXXXXXXX`, `+8801XXXXXXXXX`,
Dhaka landlines like `02-XXXXXXXX`. Spaces and dashes are ignored.
Invalid numbers produce a clear "INVALID" report instead of a crash.

**Honest limits.** This is *prefix/carrier metadata only*. It does **not**
and cannot show:

- the SIM owner's name or NID (that data exists only with the operators
  and BTRC; no public tool or API has it),
- the phone's live location.

Also note: because of Mobile Number Portability (MNP), a number's *current*
operator can differ from the operator its prefix was allocated to — the
report says this on every mobile result.

---

## Tool 2 — `location_link.py` · consent-based location sharing link

**What it does.** A tiny web server (Python standard library only) that
creates personal location-sharing links:

1. The owner creates a link (protected by an admin key).
2. The owner sends the link to a family member / their own other phone.
3. The visitor sees an honest page (Bengali + English) explaining that
   tapping the button shares **their** location with the person who sent
   the link. Nothing is captured before the tap; there is a Cancel option;
   there is no brand impersonation and no hidden tracking.
4. Only if the visitor taps **"📍 Share my location"** *and* approves the
   browser's own location-permission prompt does the browser send its
   GPS coordinates to the server.
5. The server appends the result to `locations.jsonl` and, if configured,
   sends the owner a Telegram message with a Google Maps link.

**Setup & run**

```bash
# required to create links:
export ADMIN_KEY='choose-a-secret-key'

# optional Telegram notification:
export LOC_BOT_TOKEN='123456:ABC...'        # your bot token
export LOC_OWNER_CHAT_ID='123456789'        # your Telegram chat id

export PORT=8090                            # optional, default 8090
export LINK_TTL_HOURS=24                    # optional, link lifetime

python3 location_link.py
```

**Create a link**

```bash
curl 'http://localhost:8090/new?key=choose-a-secret-key'
# -> {"token": "...", "url": "/l/...", "expires_at": "..."}
```

Send `http://<your-host>:8090/l/<token>` to the person. When they share,
an entry like this lands in `locations.jsonl`:

```json
{"time": "...", "token": "...", "lat": 23.8103, "lon": 90.4125,
 "accuracy": 15.0, "ip": "...", "user_agent": "..."}
```

…and (with Telegram configured) the owner receives:

```
📍 নতুন লোকেশন পাওয়া গেছে
সময়: 2026-11-25 10:30 AM
Google Maps: https://www.google.com/maps?q=23.8103,90.4125
Accuracy: ~15m
```

**Endpoints**

| Endpoint | Purpose |
|---|---|
| `GET /new?key=<ADMIN_KEY>` | Create a link token (JSON). Disabled with a clear error if `ADMIN_KEY` is unset. |
| `GET /l/<token>` | The consent page. Friendly error page for unknown/expired tokens. |
| `POST /api/loc/<token>` | Receives `{lat, lon, accuracy}` after the visitor's tap + permission. |
| `GET /health` | Returns `200 ok`. |

**Notes**

- Tokens are stored in `tokens.json` (written atomically) next to the script
  and expire after `LINK_TTL_HOURS`.
- If the Telegram variables are unset, locations are simply logged to
  `locations.jsonl`; a failed Telegram call never crashes the server.
- For the link to work from another phone, the server must be reachable
  from that phone (same network, a tunnel, or a hosted deployment), and
  browsers only allow geolocation on **HTTPS** pages (or `localhost`) —
  so for real use, put it behind HTTPS.
- Honest limit: this only works with the visitor's knowledge and tap.
  It is a family/own-device location-sharing tool, not a tracker.

---

## Files

| File | Description |
|---|---|
| `number_info.py` | Tool 1 — number info lookup (needs `phonenumbers`) |
| `location_link.py` | Tool 2 — consent location link server (stdlib only) |
| `tokens.json` | Created at runtime by Tool 2 (link tokens) |
| `locations.jsonl` | Created at runtime by Tool 2 (shared locations) |
