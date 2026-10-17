
import os
import json
import time
import threading
import secrets
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse
from flask import request, Response, jsonify, render_template_string

CHECK_INTERVAL = 180
TIMEOUT_SECONDS = 15

_lock = threading.Lock()
_started = False
_status = {}
_previous = {}


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Private Uptime Dashboard</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0b1020;color:#edf2ff;font:15px Arial,sans-serif}
main{max-width:900px;margin:35px auto;padding:18px}
h1{margin-bottom:6px;font-size:28px}
.sub{color:#9aa8c7;margin-bottom:25px}
.card{background:#151d32;border:1px solid #293652;border-radius:16px;
padding:20px;margin:14px 0;overflow-wrap:anywhere}
.name{font-size:19px;font-weight:bold;margin-bottom:9px}
.status{font-weight:bold;margin:8px 0}
.up{color:#56e39f}.down{color:#ff737d}.unknown{color:#ffd479}
a{color:#8cbaff}
.small{color:#a9b5d0;font-size:13px;line-height:1.7}
button{border:0;border-radius:9px;padding:11px 15px;background:#789cff;
color:#081126;font-weight:bold;cursor:pointer}
</style>
</head>
<body><main>
<h1>📡 Uptime Dashboard</h1>
<div class="sub">Private service monitor · Checks every 3 minutes</div>
<button onclick="location.reload()">↻ Refresh page</button>
<div id="items"><div class="card">Loading status…</div></div>
<div class="small">The page refreshes every 30 seconds. Actual service checks run on the server.</div>
</main>
<script>
async function loadStatus(){
  const box=document.getElementById("items");
  try{
    const r=await fetch("/uptime/api",{cache:"no-store"});
    if(!r.ok) throw new Error("HTTP "+r.status);
    const data=await r.json();
    box.innerHTML="";
    for(const s of data.services){
      const card=document.createElement("div");
      card.className="card";
      const name=document.createElement("div");
      name.className="name"; name.textContent=s.name;
      const status=document.createElement("div");
      status.className="status "+(s.state==="ONLINE"?"up":s.state==="OFFLINE"?"down":"unknown");
      status.textContent=(s.state==="ONLINE"?"🟢 ":s.state==="OFFLINE"?"🔴 ":"🟡 ")+s.state;
      const link=document.createElement("a");
      link.href=s.url; link.target="_blank"; link.rel="noopener noreferrer";
      link.textContent=s.url;
      const details=document.createElement("div");
      details.className="small";
      details.textContent="HTTP: "+(s.http_code??"—")+" · Response: "+
        (s.latency_ms==null?"—":s.latency_ms+" ms")+" · Checked: "+(s.checked_at||"Not checked yet")+
        (s.error?" · "+s.error:"");
      card.append(name,status,link,details); box.appendChild(card);
    }
  }catch(e){box.textContent="Unable to load status. Please refresh and try again."}
}
loadStatus();
</script>
</body></html>
"""


def _private_auth():
    expected_user = os.environ.get("DASHBOARD_USER", "").strip()
    expected_password = os.environ.get("DASHBOARD_PASSWORD", "")

    # Fail closed: never expose the dashboard if credentials are missing.
    if not expected_user or not expected_password:
        return False, True

    auth = request.authorization
    if not auth:
        return False, False

    valid = (
        secrets.compare_digest(auth.username or "", expected_user)
        and secrets.compare_digest(auth.password or "", expected_password)
    )
    return valid, False


def _protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        allowed, not_configured = _private_auth()
        if not_configured:
            return "Dashboard credentials are not configured.", 503
        if not allowed:
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Private Uptime Dashboard"'}
            )
        return view(*args, **kwargs)
    return wrapped


def _load_urls():
    raw = os.environ.get("UPTIME_URLS", "").strip()
    if not raw:
        raw = (
            "https://mytronuserbot.onrender.com,"
            "https://sakshamxmusic.onrender.com"
        )

    urls = []
    for item in raw.split(","):
        url = item.strip().rstrip("/")
        parsed = urlparse(url)

        # Accept only public HTTPS URLs; reject credentials and malformed hosts.
        if (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            urls.append(url)

    return list(dict.fromkeys(urls))


def _check_url(url):
    started = time.monotonic()
    code = None
    error = None

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Private-Uptime-Monitor/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                code = response.status
        except urllib.error.HTTPError as exc:
            # An HTTP response, even 404/500, means the host responded.
            code = exc.code
        state = "ONLINE" if code is not None and 200 <= code < 400 else "OFFLINE"
        if code is not None and code >= 400:
            error = "HTTP response indicates an endpoint/server error"
    except Exception as exc:
        state = "OFFLINE"
        error = type(exc).__name__

    latency = round((time.monotonic() - started) * 1000)
    return {
        "url": url,
        "name": urlparse(url).hostname or url,
        "state": state,
        "http_code": code,
        "latency_ms": latency,
        "error": error,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def _telegram_alert(token, chat_id, message):
    if not token or not chat_id:
        print("Uptime alert skipped: bot token/chat ID missing.")
        return

    payload = urllib.parse.urlencode({
        "chat_id": str(chat_id),
        "text": message,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status >= 400:
                print("Uptime alert failed with HTTP", response.status)
    except Exception as exc:
        print("Uptime Telegram alert failed:", type(exc).__name__)


def _monitor_loop(token, chat_id):
    global _status, _previous

    urls = _load_urls()
    if not urls:
        print("Uptime monitor: no valid HTTPS URLs in UPTIME_URLS.")
        return

    while True:
        for url in urls:
            result = _check_url(url)

            with _lock:
                old_state = _previous.get(url)
                _status[url] = result
                _previous[url] = result["state"]

            # First result establishes baseline; only notify on later changes.
            if old_state is not None and old_state != result["state"]:
                if result["state"] == "OFFLINE":
                    message = (
                        "🔴 SERVICE DOWN\n\n"
                        f"Service: {result['name']}\n"
                        f"URL: {url}\n"
                        f"HTTP: {result['http_code'] or 'No response'}\n"
                        f"Checked: {result['checked_at']}"
                    )
                else:
                    message = (
                        "🟢 SERVICE BACK ONLINE\n\n"
                        f"Service: {result['name']}\n"
                        f"URL: {url}\n"
                        f"HTTP: {result['http_code']}\n"
                        f"Checked: {result['checked_at']}"
                    )
                _telegram_alert(token, chat_id, message)

        time.sleep(CHECK_INTERVAL)


def register_dashboard(flask_app, bot_token, owner_id):
    global _started

    @flask_app.route("/uptime")
    @_protect
    def uptime_page():
        return render_template_string(PAGE)

    @flask_app.route("/uptime/api")
    @_protect
    def uptime_api():
        with _lock:
            services = list(_status.values())
        return jsonify({
            "interval_seconds": CHECK_INTERVAL,
            "services": services,
        })

    with _lock:
        if not _started:
            _started = True
            thread = threading.Thread(
                target=_monitor_loop,
                args=(bot_token, owner_id),
                daemon=True,
                name="uptime-monitor",
            )
            thread.start()
              
