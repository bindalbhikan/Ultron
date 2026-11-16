# 10. Small ones — orjson, pypdfium2 text, pydantic-settings

**Status**: ⏳

* **orjson** in place of `json` where answers or caches are big (portal job lists, phone answers): 5-10x faster,
  dates and numpy values handled.
* **pypdfium2** text in place of **pypdf** for the courier POD PDFs (`scripts/phone/rework_sms.py`): pypdfium2 is
  already installed for the labels, reads text better and faster. Not PyMuPDF: AGPL.
* **pydantic-settings** for settings and secrets (`.env`, repo variables, `agent.toml`): typed and checked at
  start, a missing or wrong setting named before a run begins instead of halfway.
