# Myntra Sale & Return Analysis - context for agents

Bindal Exports sells on Myntra through three seller accounts. This folder builds one Excel workbook that
analyses sales, cancellations, RTO, customer returns, exchanges and Myntra payments for
**orders placed Apr-25 to Sep-26**. The three accounts are always analysed **as one portal**.

| Account | Myntra seller id |
|---|---|
| MAIN | 19170 |
| DBCC | 32207 |
| FMCC | 35426 |

## Folder layout

```
Input/
  MYNTRA ORDERS ALL ACCOUNTS APR-25 TO SEP-26.xlsx    order lines, all 3 accounts (279,912 rows)
  MYNTRA RETURNS ALL ACCOUNTS APR-25 TO SEP-26.xlsx   returns + RTO lines (103,076 rows)
  MasterSheet.xlsx                                     sheet "Master": SKU master (MY SKU, FINAL SKU ...)
  OCT-26 RETURNS/                                      returns report 01-Oct-26..26-Oct-26 per account,
                                                       downloaded from the portal job history
Output/
  MYNTRA SALE RETURN ANALYSIS APR-25 TO SEP-26.xlsx    the deliverable
scripts/
  1_load_inputs.py          Input xlsx -> parquet (orders, returns, master)
  2_load_payments.py        Myntra payment exports -> parquet
  3_build_workbook.py       all logic + the workbook
  fetch_returns_from_job_history.py   download existing Myntra returns report jobs (never new ones)
```

## External sources

* **Payment exports** (from the Ultron bot's SPF setup):
  * `G:/My Drive/BINDAL EXPORTS/SPF/MYNTRA/input/<MAIN|DBCC|FMCC>/payment.xlsx` - up to 25-Sep-26
  * `G:/My Drive/BINDAL EXPORTS/SPF/MYNTRA/payment/myntra-payments-TOTAL-*.csv` - 11-Jun to 08-Oct-26, one per account
  * `Input/PAYMENTS AUG-OCT-26/` - 01-Aug to 30-Oct-26, downloaded live by the Ultron bot:
    `python scripts/myntra/myntra_payments.py <from> <to> <out folder>` (run from the bot repo; read-only, uses the
    saved sessions; same API as the QUIRY Chrome tool `myntra-payment-export.js`)
  * The sets overlap: rows are de-duplicated on payment date + UTR + order type + order line + return id + amount.
  * Dates come in two formats (with and without time): parse with `format="mixed"`, otherwise the csv dates
    are lost and the overlap is counted twice.
* **Daily returns reports** of the bot: `G:/My Drive/BINDAL EXPORTS/AGENT WORK/MYNTRA DAILY REPORTS/<date>/<ACC> Returns <date>.csv`
  (23-Oct-26 onwards), used to cover the days after the Oct job.
* **Bot repo** (Ultron): `G:/My Drive/BINDAL EXPORTS/AGENT/AGENT-ULTRON-BINDAL`. `src/ultron/workings/myntra_spf/engine.py`
  documents the payment report (Forward / Reverse / NOD lines). `docs/bots/myntra-history.md` and
  `myntra-reports.md` describe how order/return reports are fetched.

## Rules the user set

* **Never ask the Myntra portal for a new report** without the user's say-so. To fill missing data, download a
  report job that already exists in the portal job history (`scripts/fetch_returns_from_job_history.py`; it
  loads the bot repo's `.env` and needs `PYTHONPATH=src`, run from the repo folder). A partial range is fine.
* Workbook look: **yellow family, black text** (header `#FFC000`, sub-header / totals `#FFE699`, block title
  `#FFF2CC`). No blue, no white text.
* **No comments or explanation text in the sheets**, no emoji / symbols (no arrows, rupee sign, bullets),
  no charts, no KPI tiles, no wrap text. It must look hand-made. Amounts are plain numbers; negative growth
  is shown with a minus sign.
* **Alignment:** every value (text, numbers, %, dates) left + middle; headers center + middle.
* Few sheets, each easy to read. Every table has a title or grouped header so it is clear what it shows.
* Everything written to files is in English. (The user chats in Hinglish.)

## Definitions (used in every sheet)

* **Sale value** = `final amount` (what the customer paid). MRP and seller price are in RAW DATA.
* **FINAL STATUS** per order line:
  * Customer Return = returns report line of type Return (exchanges included; no separate Exchange status)
  * Cancelled = portal status F (SUB STATUS splits "before dispatch" and "after dispatch, came back as RTO" -
    a post-pack cancellation shows up in the returns report as RTO)
  * RTO = portal status RTO, or an RTO line in the returns report
  * Delivered = portal status C and no return line
  * In Transit = SH / PK / WP
* **Exchange replacement orders** (order release id = some `exchange_id`) are flagged in RAW DATA but counted
  like any other order line (user's rule: gross = every order line).
* **Net sale** = Delivered only. Gross = all order lines.
* Cancel % = of gross; RTO % = of dispatched (gross - cancelled); Return % = of delivered to
  customer (delivered + returns).
* Analysis is by **ORDER MONTH** (what happened to each month's orders). Returns are merged from the Apr-25..Sep-26
  report, the Oct-26 job and the daily files; one row per order line, the newest file wins.
* **SKU mapping**: MasterSheet "Master", MYNTRA channels, keyed on `MYNTRA SKU CODE` (fallback seller SKU =
  `Channel Listing SKU Code`) -> MY SKU, FINAL SKU, FINAL MY SKU, DESIGN-NO. 100% match.
* **Payment mapping** on `order_line_id`: Forward = sale settlement, Reverse = return/RTO debit (negative),
  NOD = SPF claims / adjustments. NET SETTLEMENT = forward + reverse + NOD.
* Brands / categories with fewer than 500 orders are grouped as "Others" on the BRAND / CATEGORY sheets.

## Workbook sheets

All numbers on MONTH / BRAND / CATEGORY / REASONS and the first PAYMENT table are COUNTIFS / SUMIFS formulas on
RAW DATA ("Others" = total less the named rows). Only the payment-month cash table is values (its source is not in RAW DATA).


| Sheet | Content |
|---|---|
| RAW DATA | one row per order line: ids, style, SKU + master SKUs, brand, category, size, prices, final status, reason, dates, courier, payment columns |
| MONTH WISE | one table: SALE / CANCELLED / RTO / CUSTOMER RETURN / NET SALE (incl. MoM) / LAST YEAR (YoY) / PAYMENT (Net Received) per month |
| BRAND WISE | all-brands table, then one block per brand with all 18 months + total |
| CATEGORY WISE | same as BRAND WISE for article type |
| BRAND CATEGORY WISE | same as BRAND WISE per brand + category pair ("DressBerry - Tops"), pairs under 500 orders = Others |
| REASONS | customer return and cancellation reasons side by side |
| PAYMENT | (1) payment against orders by order month, (2) payment received by payment month |
| INPUT LOG | every input file per account: rows, date field, from / to, plus the merged "used" rows |

## Rebuilding

```
W=<any work folder>; mkdir -p "$W/pq"
python scripts/1_load_inputs.py "$W"
cd "$W" && python "G:/My Drive/MYNTRA ANALYSIS/scripts/2_load_payments.py"       # writes ./pq/pay_*.parquet
python scripts/3_build_workbook.py "$W" "G:/My Drive/MYNTRA ANALYSIS/Output/MYNTRA SALE RETURN ANALYSIS APR-25 TO SEP-26.xlsx"
```

After the build, open the file once in Excel (or via COM: Workbooks.Open, CalculateFull, Save) so the
formula results are stored; otherwise Drive preview / Google Sheets show 0 everywhere.

The build takes about 2 minutes (RAW DATA is ~280k rows, the file ~60 MB). Close the workbook in Excel first.

## Known state (28-Oct-2026)

* Payment data runs to 30-Oct-26; Sep-26 orders are settled except 4 lines.
* Sep-26 returns include the Oct-26 job (01-26 Oct) and daily files to 27-Oct; Sep return % is 29.2%, in line with
  other months. Aug-Sep 26 can still rise a little as late returns come in.
* About 1.6% of return lines belong to orders placed before Apr-25; they are not in RAW DATA.

# Flipkart Sale & Return Analysis (added 01-Nov-2026)

`FLIPKART SALE RETURN ANALYSIS FEB-26 TO OCT-26.xlsx`, built by the Ultron repo:
`src/ultron/workings/business_report/flipkart.py` (`raw_data`, `build`). Same look and rules as the
Myntra workbook; every number is a SUMIFS on RAW DATA, written with its value.

* Inputs: Flipkart Seller Hub `Orders` reports (one row per order item, no price) Feb-26..Oct-26 and
  `Returns` reports (one row per return line, cancelled returns left out). Jul-26 has no orders
  file with data: the month is left out (not shown as zero). Feb-26 starts 03-Feb, Oct-26 ends 30-Oct.
* FINAL STATUS: Customer Return (return line customer_return), RTO (courier_return), Cancelled
  (CANCELLED / REJECTED), Delivered, Return Type Pending (RETURNED without a return line whose
  return reason does not tell the type), In Transit. Quantities are the QUANTITY column.
* Brand and design from MasterSheet (channel FLIPKART, 100% match); CATEGORY = the article type
  Myntra lists the same design under.
* Values and payments: not yet (no price in the Orders report). The `Settled Transactions` payment
  reports are being back-filled into AGENT WORK/PORTAL REPORTS; the workbook is rebuilt with value
  and payment columns once they are in.
* Sheets: RAW DATA, MONTH WISE, BRAND WISE, CATEGORY WISE, REASONS (customer return and RTO
  reasons), INPUT LOG.
