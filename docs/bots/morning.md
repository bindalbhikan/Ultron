# Morning report — `python run.py morning`

**When**: 9:30 AM IST daily (`morning.yml`, started by the worker's cron, `SCHEDULE` in `worker/src/worker.js`). By hand: run the workflow, optionally with a `day`.

**Result**: one Telegram message, nothing written anywhere: yesterday's sale in units per channel
against the same weekday a week before, with the change in %, the total and yesterday's cancels.

* OMSGuru: every channel on its own line, the Myntra accounts apart (MAIN = channel MYNTRA, PPMP,
  DBCC = DressBerry CC, FMCC = Fashfun Murcia CC); units by order date, each day read on its own
  (`units_by_channel`, shared with the sale report; a window near the list's ~3,000-line limit is
  read in two halves). Cancelled = item status Cancelled / Cancelled Before Shipping / Removed
  Before Shipping.
* Flipkart FBF from Seller Hub and Myntra SJIT from the partner portal, as in the sale report; the
  morning never asks Myntra itself: it waits up to 35 minutes (`SJIT_WAIT_MINUTES`) for the 30-day order
  report the 9:30 AM `myntra-reports` run asks for (`ask=False`, since 16 Nov 2026); when none comes or it
  holds yesterday only in part, a new one is asked for and waited for (the workflow has 85 minutes).
* 2-3 lines on the numbers in English from the agent's free model (Workers AI, `ultron.core.llm`);
  left out when the model is not available.
* **Sudden drops** (plan E5): a channel that sold `DROP_MIN_UNITS` (20)+ units on last week's
  same day and sold nothing yesterday (🔴, check the listing / account) or fell `DROP_PCT` (40) %+ (⚠️).
* WhatsApp (when `CALLMEBOT_PHONE` / `CALLMEBOT_APIKEY` are set): the table and drops also go to the owner's own number as text, without the model's lines.
* Returns are not in it: the sale report's RETURN is typed by hand.
