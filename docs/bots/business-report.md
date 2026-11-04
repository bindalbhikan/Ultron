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
  Months kept on 3 Nov 2026: Myntra orders Apr-25 on (older refused; payments Jan-25), Flipkart orders
  Feb-26 on + the tax Sales Report (items before Feb-26 come from its events, SOURCE = Sales
  report; Sales Report Archived for Nov-25, Dec-25; payments May-26 on), AJIO orders from 13 Dec 2025 (Dec-25 PARTIAL, from the Ads Gap
  working's old download; the portal answers "No records found" before Jan-26; ledger from 28 Feb 2026).
* **Flipkart and AJIO start at Apr-25** (`START` in `pipeline.py`; owner's rule, 3 Nov 2026). AJIO's order reports of Apr-25 to Aug-25
  and Dec-25 come from the Tuesday Working folders (weekly 30-day downloads, the newest line wins); days none reaches (Aug 30 to
  Sep-25) from OMSGuru, SOURCE = OMSGuru, their values `-`. Flipkart before Feb-26 is the Sales Report + OMSGuru's status. Flipkart has no
  payment before Oct-25: `-`. Later months before the portal's
  reports come from the owner's monthly files, kept as `<PORTAL> MONTHLY REPORT <MON-YY>.xlsx` in the same month folders:
  Flipkart Oct-25 to Apr-26 (settled order items: the payment of months with no Settled Transactions file, and the items
  of Nov-25 and Dec-25; SOURCE = Monthly file), AJIO Oct-25 to Jan-26 (order lines the order report does not have).
  Checked against the portal's reports: Flipkart's settlement is the same item by item (May-26 to Sep-26), AJIO's price is
  the same on every line both have.
* **Flipkart's numbers, by order date** (owner's rule, 4 Nov 2026): every month's tax Sales Report is merged (a month's file also
  holds earlier months' orders) and each order item counted once, in the month of its own order date, with FBF and non-FBF together.
  SALE VALUE = **Price before discount**, in every month. Cancelled = as many Cancellation rows as Sale rows: a Sale, a
  Cancellation and a second Sale is one item invoiced again, still sold (9,331 items, 3,422 of them returned later). Cancelled is now
  counted, not `-`, in the months with no Orders report; an item never invoiced is in no report there, so Gross and Cancelled stay low
  (Nov-25: 5,963 against Earn More's 6.3k). From Feb-26 such items come from the Orders report, without a value.
  Earn More's rupees run above every price column of the Sales Report (Nov-25: 25.21 L against 30.57 L; not explained), so its
  figures are read from the portal itself: sheet **EARN MORE**, first to open (`FlipkartClient.earn_more`, order months with data, Nov-25 on;
  older months `-`). Checked against the screen: Aug-26 9,040 / 42.87 L, cancellations 2,506 / 12.05 L, returns 1,799 / 8.51 L,
  net 4,735 / 22.31 L. Its Cancellations hold RTO. MONTH WISE and the other sheets stay on RAW DATA, the lines of the reports.
  `G:\My Drive\FLIPKART` holds the same Sales Reports from Jan-25 on, with no row PORTAL REPORTS lacks (checked 4 Nov 2026).
* **Flipkart and AJIO count by quantity, not by order** (owner's rule, 4 Nov 2026): every count sums QTY. A line of which only some
  units came back or were cancelled is two rows of the same id (`split_part`): those units with their status, the rest as they
  were, money shared by quantity, the totals unchanged. Counted in the INPUT LOG. Myntra's report is one unit per line.
* **OMSGuru's status** (`business_report/oms.py`, owner's rule, 3 Nov 2026): `<PORTAL> OMSGURU REPORT <MON-YY>.xlsx` in the
  same month folders, from `portal-reports` (kinds `omsguru`): channels Flipkart, Ajio and Ajio Api (Ajio up to Feb-26, Ajio
  Api after). Lines match on order id + FINAL SKU; the workbook shows OMS STATUS. Delivered, Cancelled and Cancelled Before
  Shipping mean the same in the portals' reports (checked on 43,000 one-line orders); Return Init / Return Received =
  customer return; Cancelled Return Received and Cancel Init = RTO. A return, RTO or cancellation it shows replaces
  Delivered, In Transit or Return Type Pending; a line a return report settled is not changed. It is not whole (no Flipkart
  FBF, most orders cancelled before shipping are missing), so it adds lines only to Flipkart months with no Orders
  report (Oct-25 to Jan-26, SOURCE = OMSGuru: mostly RTO).
* **AJIO payment before the ledger** (Oct-25 to Feb-26, the SRM ledger starts on 28 Feb 2026): as the owner's monthly files
  work it out, Invoice Value less FWD B2B Invoice Amt of returns, PAYMENT STATUS = As per monthly file. Against the files'
  own TOTAL PAYOUT: within about 1 %. Against the ledger, Mar-26 to Oct-26, order-month totals: the ledger runs 0-6 % above it,
  Jul-26 33 % (not explained). What is due, not the bank; their EXP sheets are not taken off.
* **Payment match, Flipkart and AJIO** (PAYMENT sheet, by payment month). Flipkart: Order Settlement, SPF / Ads / Storage, Net Bank Paid
  (Settled Transactions' `Summary of report`, Net Bank Settlement (A); before May-26 the total row of the monthly file), the
  transfers that file lists (rounded by Flipkart) and the difference. AJIO: G4, IC and the other ledger lines give Net Due, KP is the bank
  payment itself, and the Difference is 0 in every month from Mar-26 (the last month: cleared, payment still to come); before
  the ledger the months are as per the monthly files, with their EXP sheet, and no bank figure. A PAYMENT MATCH block goes from the
  bank to NET SETTLEMENT in RAW DATA step by step. Net Received in MONTH WISE = NET SETTLEMENT of every line of the order month
  (for these two portals; Myntra keeps Delivered + Customer Return), so it is by order month and never equals one payment month.
* **A number that is not known shows `-`, never 0, and is named in the INPUT LOG** (`Report.unknown`). Cancelled: AJIO Oct-25 to
  Dec-25 (those sources leave out most lines cancelled before shipping, so Gross is low in those months). Payment: a Flipkart order month with no payment on any sold line, PAYMENT STATUS = No Payment Report.
* AJIO: a status is as old as its file, so a line Shipped over 60 days ago with no return since counts as Delivered (named
  in the INPUT LOG).
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
