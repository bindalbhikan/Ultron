# 10. Small ones — orjson, pypdfium2 text, pydantic-settings

**Status**: ✅ 17 Nov 2026 — pypdfium2, pydantic-settings, orjson.

* **pypdfium2** in place of **pypdf** for the courier POD PDFs (`scripts/phone/rework_sms.py`) ✅ 17 Nov 2026.
  pypdfium2 (PDFium, C++) was already installed for the labels; not PyMuPDF (AGPL). Checked first: 13 real POD
  PDFs from the SMS sheet's links (Delhivery, Xpressbees, Shadowfax ...), the text of each read both ways and
  given to the phone sheet's own `parsePod` (Code.gs, run in Node): every AWB, type and status the same (1 to 29
  AWBs a PDF). pypdf is out of `pyproject.toml` and `uv.lock`.
* **pydantic-settings** for settings ✅ 17 Nov 2026: `workings/core/settings.py` `check_settings`, called by
  `run_bot` before every bot runs. The settings a bot reads are found in its own code (its `num` / `flag` /
  `required` calls and workings/core's; 142 over the 35 bots) and become one typed pydantic-settings model read
  from the environment and `.env` (blank = unset, as GitHub passes an unset variable). A number or yes / no setting
  in another shape stops the run at once, named (before, `SALE_REPORT_DAYS=l0` quietly fell back to the default
  and the run went on with other numbers than meant); a missing required setting is named in the log (required()
  still stops the run when that path is reached). The same names (`env`, `num`, `flag`, `required`) stay.
  Checked: every bot with the local `.env` and the repo's variables passes; `tests/test_settings.py`.
* **orjson** ✅ 17 Nov 2026: `ultron/core/jsonx.py` `loads`, used by `core/http.json_of` for every portal answer (and
  the Myntra partner portal's curl_cffi answers). Two cases go to json on purpose: text orjson refuses (NaN) and text
  holding a run of 20 digits or more — orjson reads a number beyond 64 bits as a float (10^30 came back 1e+30), json
  keeps it exact, and a long id must never come back rounded. The check is one C pass (`bytes.translate`); with it a
  20,000-job answer reads 1.6x faster than with json (a regex check had made it slower than json). Not pure Python:
  the core falls back to json. Files the bots write keep the json module (their exact format).
