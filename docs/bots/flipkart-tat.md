# Flipkart TAT — `python run.py flipkart-tat`

6 PM daily, started by the worker's cron (`fktat` in `worker/src/worker.js`; GitHub's own schedule ran
it 6 hours late). On demand: `/fktat` or Flipkart > Flipkart TAT in the bot menu. The AJIO TAT working for Flipkart,
**sheet only**: no Flipkart ticket, no form.

**Result**: `AGENT WORK/FLIPKART/FLIPKART_TAT_MASTER.xlsx` (Summary, TAT Report, Late Orders),
updated in place every run, plus a short Telegram summary. The hand-made `FK Working Sheet.xlsx`
in the same folder is not touched.

- Orders: OMSGuru channel `FLIPKART_CHANNEL_IDS` (37863), the last `FK_TAT_DAYS` (4) days, plus
  master orders still waiting for pickup (Ekart tracked for up to 15 days).
- Deadline: OMSGuru's **SLA Date** of the order (Flipkart's dispatch-by, usually 4 PM), not AJIO's
  10:10 rule.
- Processing: on time when Ready to ship by the end of the SLA day.
- Pickup: Ekart's first movement scan after "Shipment Created" (e.g. "Dispatched to MotherHub"),
  on time when by the SLA time.
- Status rules, columns and colours are the AJIO engine's (`ajio_tat/tat_engine.py`).

Options: `--days N`, `--from` / `--to YYYY-MM-DD`, `--no-drive` (local master in output/flipkart_tat),
`--no-telegram`.
