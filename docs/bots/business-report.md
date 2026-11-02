# Business reporting — `python run.py business-report`

**When**: after every `portal-reports` run (the 2nd, back-fills) and every return analysis run (the
10th / 15th), as `workflow_run` of `business-report.yml`. By hand: Menu > Reports & MIS > Business report,
`/businessreport [PORTALS] [FROM [TO]]`, or the workflow (inputs `portals`, `from`, `to`, `no_upload`). A failed run goes to "AI fix on failure" (`ci-fix.yml`: Claude Code, else Gemini).

* The owner's sale / return / payment analysis (Drive `AGENT WORK/BUSINESS REPORTING`, the rules in
  `docs/bots/business-report-context.md`, taken over from the hand-run scripts on 1 Nov 2026; the old
  Myntra script is kept in `scripts/legacy/myntra_build_workbook.py`), one workbook per portal:
  `<PORTAL> SALE RETURN ANALYSIS <FIRST MON-YY> TO <LAST MON-YY>.xlsx`; the portal's older one goes
  to the Drive trash.
* Inputs: every month of Drive `AGENT WORK/PORTAL REPORTS` from `--from` (default 2025-01; a portal
  starts where its reports do) to last month, and `BUSINESS REPORTING/MasterSheet.xlsx`.
  Months kept on 2 Nov 2026: Myntra orders Apr-25 on (older refused; payments Jan-25), Flipkart orders
  Feb-26 on + the tax Sales Report from Jan-25 (items before Feb-26 come from its events, SOURCE = Sales
  report; payments May-26 on), AJIO orders from 13 Dec 2025 (Dec-25 PARTIAL, from the Ads Gap
  working's old download; the portal answers "No records found" before Jan-26; payments Feb-26).
* The same layout for every portal (`business_report/workbook.py`): RAW DATA, MONTH WISE (SALE,
  CANCELLED, RTO, CUSTOMER RETURN, NET SALE with value, ASP, MoM; LAST YEAR once 13 months are in;
  PAYMENT), BRAND WISE, CATEGORY WISE, BRAND CATEGORY WISE (all together, then one block per group,
  every month; small groups = Others), REASONS, PAYMENT (against orders by order month, then cash by
  payment month), INPUT LOG. Every number is a SUMIFS on RAW DATA written with its value.
  Values that differ only in letter case become one spelling (Excel's SUMIFS ignores case).
* Per portal: `myntra.py` (the owner's FINAL STATUS and payment rules), `flipkart.py` (Orders +
  Returns + Settled Transactions; Return Type Pending when the return line is missing),
  `ajio.py` (order report + RTV + SRM ledger: G4 = received, by REFERENCE = Seller Invoice No, shared
  over the invoice's lines by invoice value; IC = reversed, by INVOICE REFERENCE NUMBER = the DOCNO of
  that invoice's G4, shared by the credit note value of its returned lines; Net Payout = G4 + IC, other
  ledger types shown apart; money not reaching an order line is named in the INPUT LOG). Category of Flipkart and AJIO = the article
  type Myntra lists the same design under.
* Telegram: one line per portal (months, qty, net %, return %, RTO %).
