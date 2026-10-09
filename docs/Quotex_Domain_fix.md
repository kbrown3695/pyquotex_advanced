# Quotex Domain Migration Fix — 2026-10-09

## Summary

The vendored `pyquotex` library was hard-coded to `qxbroker.com`, a domain
that no longer exists on the public internet. This broke Quotex auto-login
and WebSocket streaming. The fix migrates HTTP to `quotex.com` and the
WebSocket backend to `ws2.quotex.io`.

**Status:** ✅ Verified working — demo login succeeds, balance fetched
($10000), 4 OTC pairs streaming 1m candles.

---

## Symptoms

Running `python engine.py` produced:
[ERR] Auto-login timeout (>60s)
[ERR] Reconnection error: HTTPSConnectionPool(host='qxbroker.com', port=443):
Max retries exceeded ... Failed to resolve 'qxbroker.com'
([Errno 11001] getaddrinfo failed)
♻️ Stream idle 91s > 90s — reconnecting

Then, after fixing DNS, a second-layer failure appeared:
[ERR] Re-login failed: Websocket connection rejected.

Two distinct problems, the second hidden behind the first.

---

## Root cause

### Layer 1 — `qxbroker.com` is dead

Verified against **every** resolver — it's not an ISP issue:
PS> nslookup qxbroker.com
*** UnKnown can't find qxbroker.com: Non-existent domain

PS> nslookup qxbroker.com 8.8.8.8
*** dns.google can't find qxbroker.com: Non-existent domain

PS> ping qxbroker.com
Ping request could not find host qxbroker.com.

By contrast, the current live domains resolve fine:

| Domain | Resolves | IP |
|---|---|---|
| `qxbroker.com` | ❌ NXDOMAIN | — |
| `quotex.com` | ✅ | 104.18.40.221 / 172.64.147.35 |
| `quotex.io` | ✅ | 104.18.39.143 / 172.64.148.113 |
| `qxbroker.io` | ✅ | 15.197.148.33 (redirect/parked) |
| `ws2.quotex.io` | ✅ | 104.18.39.143 |
| `ws2.quotex.com` | ⚠️ wildcard | same edge as `quotex.com` |

### Layer 2 — `*.quotex.com` is wildcarded on Cloudflare

After pointing `host = "quotex.com"`, the code built:
wss://ws2.quotex.com/socket.io/?EIO=3&transport=websocket


`ws2.quotex.com` **does** resolve — but only because Quotex wildcards
`*.quotex.com` to the same Cloudflare edge as the marketing site. The
origin doesn't recognize that hostname as a WebSocket backend, so
Cloudflare accepts the TCP connection and then rejects the WS upgrade.

The real WS backend lives on a **separate Cloudflare zone** — `quotex.io`:
Test-NetConnection ws2.quotex.io -Port 443
RemoteAddress : 104.18.39.143
TcpTestSucceeded : True


---

## Files changed

| File | Line | Before | After |
|---|---|---|---|
| `pyquotex/http/login.py` | 16 | `base_url = 'qxbroker.com'` | `base_url = 'quotex.com'` |
| `pyquotex/stable_api.py` | 37 | `host: str = "qxbroker.com",` | `host: str = "quotex.com",` |
| `pyquotex/api.py` | 100 | `self.wss_url = f"wss://ws2.{host}/socket.io/?EIO=3&transport=websocket"` | `self.wss_url = "wss://ws2.quotex.io/socket.io/?EIO=3&transport=websocket"` |
| `pyquotex/api.py` | 458 | `"host": f"ws2.{self.host}",` | `"host": "ws2.quotex.io",` |
| `pyquotex/ws/client.py` | 24 | `"Host": f"ws2.{self.api.host}",` | `"Host": "ws2.quotex.io",` |

**Why HTTP and WS use different TLDs:** HTTP login/static assets moved to
`quotex.com`; the WebSocket service moved to `quotex.io`. They are
separate Cloudflare zones. Do not unify them on one domain.

---

## Commands used to diagnose

```powershell
# 1. Confirm DNS death (system DNS + public resolvers)
ping qxbroker.com
ping quotex.com
nslookup qxbroker.com
nslookup qxbroker.com 8.8.8.8
nslookup quotex.com 1.1.1.1

# 2. TCP reachability
Test-NetConnection qxbroker.com -Port 443
Test-NetConnection quotex.com -Port 443

# 3. Find hard-coded strings in the vendored library
Get-ChildItem -Path D:\QuotexChart\pyquotex -Recurse -Include *.py |
    Select-String -Pattern "qxbroker"

# 4. Probe WS candidates
nslookup ws2.quotex.io
Test-NetConnection ws2.quotex.io -Port 443

# 5. Verify patch
Get-ChildItem -Path D:\QuotexChart\pyquotex -Recurse -Include *.py |
    Select-String -Pattern "qxbroker|ws2\."

    Browser cross-check (optional, most authoritative): open
https://quotex.com/en/trade, DevTools → Network → WS filter tab,
read the wss:// URL the live frontend uses.

Verification
After patching and clearing bytecode caches:

Get-ChildItem -Path D:\QuotexChart\pyquotex -Recurse -Include *.pyc |
    Remove-Item -Force
python engine.py

Expected output (confirmed 2026-10-09):
[OK] Demo balance initialized: {'uid': 93231018, 'isDemo': 1, 'balance': 10000}
[OK] ORDER_EXECUTOR wired to Quotex client
[OK] Login successful
[OK] Auto-login successful!
[OK] Subscribed AUD/CAD (OTC) to real-time price stream
[OK] Subscribed EUR/USD (OTC) to real-time price stream
[OK] Subscribed USD/PKR (OTC) to real-time price stream
[OK] Subscribed GBP/USD (OTC) to real-time price stream

No Auto-login timeout

No Stream idle > 90s — reconnecting loop

No Websocket connection rejected

Candles rendering on the chart

[WARN] get_signal_for_asset(...): cache empty is expected for the
first 1–3 minutes while the ML signal cache warms up.

No Auto-login timeout

No Stream idle > 90s — reconnecting loop

No Websocket connection rejected

Candles rendering on the chart

[WARN] get_signal_for_asset(...): cache empty is expected for the
first 1–3 minutes while the ML signal cache warms up.

pip install pyquotex
ERROR: No matching distribution found for pyquotex

So if the library is ever re-vendored / re-downloaded / regenerated, all
five edits above must be reapplied. The fastest way:
# After dropping in a fresh copy of pyquotex/:
Get-ChildItem -Path D:\QuotexChart\pyquotex -Recurse -Include *.py |
    Select-String -Pattern "qxbroker"
    Any hits = reapply the patch table above.