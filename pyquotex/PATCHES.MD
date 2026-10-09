# Vendored pyquotex patches

Upstream targets a dead domain (qxbroker.com). Reapply after any re-vendor:

| File | Original | Patched |
|---|---|---|
| http/login.py    | `base_url = 'qxbroker.com'` | `base_url = 'quotex.com'` |
| stable_api.py    | `host: str = "qxbroker.com"` | `host: str = "quotex.com"` |
| api.py           | `wss://ws2.{host}/...` | `wss://ws2.quotex.io/...` |
| api.py           | `"host": f"ws2.{self.host}"` | `"host": "ws2.quotex.io"` |
| ws/client.py     | `"Host": f"ws2.{self.api.host}"` | `"Host": "ws2.quotex.io"` |

Verified working 2026-10-09: demo login OK, $10000 balance, 4 OTC pairs streaming 1m candles.