# 8. httpx — HTTP

**Status**: ✅ 17 Nov 2026

**Why**: requests has no HTTP/2 and no async; httpx has requests' shape, HTTP/2, async (hundreds of calls at once
for a big seller) and strict timeouts. Pure Python, so the seller-neutral core still installs on Android / Termux.

**Done**
* One place: `ultron/core/http.py` — `client()` (an `httpx.Client` that follows redirects, as requests did),
  `get` / `post` / `request`, `json_of(r)` (orjson, `core/jsonx.py`), `ok(r)` (requests' `r.ok`: below 400),
  `FAILED` (requests' RequestException: `httpx.HTTPError` + `httpx.InvalidURL`), `PASSING` (ConnectionError / Timeout:
  tried again), `CONNECTION` (requests' ConnectionError alone).
* Moved, client by client: Telegram (agent and bots), GitHub, WhatsApp, the agent's model, memory, approvals,
  dashboard, phone, work schedule, OMSGuru (core client, used by every working), the VMS API (its hand-written retry
  loop onto `core/retry.py`: 3 tries, waits 2, 4 s), ERP, SRM, AJIO, Flipkart, the Myntra session store, SPF payment
  files, the AJIO pickup form, the Gemini follow-up, grouping files, `scripts/phone/rework_sms.py`,
  `scripts/myntra/myntra_session.py`. requests is left only where a library runs on it: Google Drive (google-auth's
  transport) and gspread; the hyper log records both httpx and requests calls.
* Kept: curl_cffi where a site checks the browser's TLS fingerprint (Myntra partner portal API, the couriers).
* Differences handled: redirects followed (AJIO's login still follows its own by hand, `follow_redirects=False`: the
  Reliance Origin header must not reach the AJIO callback); `r.url` is an `httpx.URL` (`str(r.url)` where text is
  meant); a string body is `content=`, a form `data=`; errors and `r.ok` as above.

**Checked** (live, read-only): Telegram getMe / getWebhookInfo; GitHub workflows and runs; OMSGuru — the whole page
check of step 9 run again through httpx: all 80 results the same as through requests (login, lists, 70 order pages,
VMS rows, Quick Returns forms); SRM login and 988 ledger lines; ERP login and 30,349 GRN rows; AJIO login (its redirects
by hand), 546 tickets, a ticket's details, the RTV report; Flipkart login, 103 report requests, the seller tier
(Payment Reports' list answers HTTP 500 through requests too: Flipkart's side); Myntra signed payout files — the same
bytes through both (and the repaired-link shape sent the same); a courier POD through `rework_sms.pod`. Tests for
each client's retries moved onto httpx errors; `tests/test_http.py`.
