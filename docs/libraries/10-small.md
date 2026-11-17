# 10. Small ones — orjson, pypdfium2 text, pydantic-settings

**Status**: 🔧 17 Nov 2026 — pypdfium2 ✅, pydantic-settings ✅; orjson goes in with httpx (step 8), client by client.

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
* **orjson** in place of `json` for the big portal answers (Myntra report jobs, SPF tickets, Flipkart / AJIO lists):
  it goes in with httpx (step 8), through one `json_of(response)` in each client, so each client is changed once.
  Files the bots write keep their exact format (`json` stays there).
