# 8. httpx — HTTP

**Status**: ⏳

**Why**: the API clients (Myntra partner portal, OMSGuru, AJIO, Flipkart, Drive, Telegram, GitHub) use
`requests`: no HTTP/2, no async. httpx has the same shape as requests, HTTP/2, async (hundreds of calls at
once for a big seller: AWB tracking, SPF claims, per-style lookups) and strict timeouts. curl_cffi stays where a
site checks the browser's TLS fingerprint.

**Plan**: client by client, the smallest first (Telegram), each with its tests and one live run.
