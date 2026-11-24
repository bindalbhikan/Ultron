"""
Return-analysis templates and final reports for Myntra (MAIN / DBCC / FMCC), Ajio and Flipkart, rendered from the order
lines of Business Reporting (reconciled.py picks the lines; this module only renders them).

Output:
    Template/<PORTAL> <MON-YY> TEMPLATE.csv
    Output/<MON-YY>/<PORTAL> SALE RETURN ANALYSIS <MON-YY>.xlsx

A line: MONTH (MM-YYYY), PORTAL, BRAND, ORDER ID, SELLER SKU CODE, MY SKU, QTY, CATEGORY, ORDER STATUS (Delivered /
Return), RETURN/EXCHANGE REASON, SALE PRICE, COST (FINAL COST of the Cost Sheet, matched on MY SKU without the size
suffix, else the whole MY SKU), STATE.

Tables are Polars, the workbook is written by xlsxwriter (docs/libraries). Every table is ordered "highest first, equal
values A to Z", as before.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime

import polars as pl

log = logging.getLogger("bindal.return_analysis")

MYNTRA_ACCOUNTS = ['MAIN', 'DBCC', 'FMCC']
COLUMNS = ['MONTH', 'PORTAL', 'BRAND', 'ORDER ID', 'SELLER SKU CODE', 'MY SKU', 'QTY', 'CATEGORY',
           'ORDER STATUS', 'RETURN/EXCHANGE REASON', 'SALE PRICE', 'COST']
# Columns of a portal's monthly data kept for the yearly report: the template columns plus STATE
DATA_COLUMNS = COLUMNS + ['STATE']
SCHEMA = {'MONTH': pl.Utf8, 'PORTAL': pl.Utf8, 'BRAND': pl.Utf8, 'ORDER ID': pl.Utf8, 'SELLER SKU CODE': pl.Utf8,
          'MY SKU': pl.Utf8, 'QTY': pl.Int64, 'CATEGORY': pl.Utf8, 'ORDER STATUS': pl.Utf8,
          'RETURN/EXCHANGE REASON': pl.Utf8, 'SALE PRICE': pl.Float64, 'COST': pl.Float64, 'STATE': pl.Utf8}
# Different brand names that are the same brand, merged in the combined reports (lower case: lower case)
BRAND_ALIASES = {'fashfun clothing': 'fashfun'}
# Master "Channel Name" values whose PORTAL LISTING DATE counts as the launch date on each portal
PORTAL_CHANNELS = {
    'MYNTRA MAIN': ['MYNTRA', 'MYNTRA PPMP'], 'MYNTRA DBCC': ['MYNTRA DBCC'], 'MYNTRA FMCC': ['MYNTRA FMCC'],
    'AJIO': ['AJIO', 'AJIO API'], 'FLIPKART': ['FLIPKART'],
}

ZONES = ['NORTH', 'WEST', 'EAST', 'SOUTH']
STATE_ZONE = {
    'Delhi': 'NORTH', 'Haryana': 'NORTH', 'Punjab': 'NORTH', 'Himachal Pradesh': 'NORTH',
    'Jammu and Kashmir': 'NORTH', 'Ladakh': 'NORTH', 'Chandigarh': 'NORTH', 'Uttar Pradesh': 'NORTH',
    'Uttarakhand': 'NORTH', 'Rajasthan': 'NORTH',
    'Maharashtra': 'WEST', 'Gujarat': 'WEST', 'Goa': 'WEST', 'Madhya Pradesh': 'WEST',
    'Dadra and Nagar Haveli and Daman and Diu': 'WEST',
    'West Bengal': 'EAST', 'Bihar': 'EAST', 'Jharkhand': 'EAST', 'Odisha': 'EAST', 'Chhattisgarh': 'EAST',
    'Assam': 'EAST', 'Arunachal Pradesh': 'EAST', 'Manipur': 'EAST', 'Meghalaya': 'EAST', 'Mizoram': 'EAST',
    'Nagaland': 'EAST', 'Tripura': 'EAST', 'Sikkim': 'EAST', 'Andaman and Nicobar Islands': 'EAST',
    'Karnataka': 'SOUTH', 'Kerala': 'SOUTH', 'Tamil Nadu': 'SOUTH', 'Telangana': 'SOUTH',
    'Andhra Pradesh': 'SOUTH', 'Puducherry': 'SOUTH', 'Lakshadweep': 'SOUTH',
}
# State codes and spellings seen in portal reports -> name used in STATE_ZONE
STATE_ALIASES = {
    'DL': 'Delhi', 'HR': 'Haryana', 'PB': 'Punjab', 'HP': 'Himachal Pradesh', 'JK': 'Jammu and Kashmir',
    'JAMMU & KASHMIR': 'Jammu and Kashmir', 'LA': 'Ladakh', 'CH': 'Chandigarh', 'UP': 'Uttar Pradesh',
    'UT': 'Uttarakhand', 'UK': 'Uttarakhand', 'RJ': 'Rajasthan', 'MH': 'Maharashtra', 'GJ': 'Gujarat',
    'GA': 'Goa', 'MP': 'Madhya Pradesh', 'DN': 'Dadra and Nagar Haveli and Daman and Diu',
    'DD': 'Dadra and Nagar Haveli and Daman and Diu',
    'DADRA AND NAGAR HAVELI': 'Dadra and Nagar Haveli and Daman and Diu',
    'DAMAN AND DIU': 'Dadra and Nagar Haveli and Daman and Diu',
    'WB': 'West Bengal', 'BR': 'Bihar', 'JH': 'Jharkhand', 'OR': 'Odisha', 'OD': 'Odisha', 'ORISSA': 'Odisha',
    'CT': 'Chhattisgarh', 'CG': 'Chhattisgarh', 'AS': 'Assam', 'AR': 'Arunachal Pradesh', 'MN': 'Manipur',
    'ML': 'Meghalaya', 'MZ': 'Mizoram', 'NL': 'Nagaland', 'TR': 'Tripura', 'SK': 'Sikkim',
    'AN': 'Andaman and Nicobar Islands', 'KA': 'Karnataka', 'KL': 'Kerala', 'KERALAM': 'Kerala',
    'TN': 'Tamil Nadu', 'TG': 'Telangana', 'TS': 'Telangana', 'AP': 'Andhra Pradesh', 'PY': 'Puducherry',
    'PONDICHERRY': 'Puducherry', 'LD': 'Lakshadweep',
}

# Return reasons are merged into these groups in the report. Rules run on the reason in lower case with "_"
# turned into spaces, in this order: the first regex that matches wins (so "wrong size" is checked before "size").
REASON_GROUPS = [
    ('Wrong Size Delivered', r'wrong size|different size|size is different'),
    ('Size Too Big', r'size.*(larg|big)'),
    ('Size Too Small', r'size.*small'),
    ('Fit Issue', r'\bfit\b'),
    ('Damaged / Defective / Missing Item', r'damag|defect|torn|faded|missing|broken'),
    ('Used / Old / Dirty Product', r'used product|looked old|dirty|stain'),
    ('Poor Quality', r'quality'),
    ('Wrong Colour Delivered', r'wrong colou?r|different colou?r received'),
    ('Colour Not As Expected', r'colou?r'),
    ('Wrong Product Delivered', r'different product|completely different|different brand'),
    ('Product Looks Different From Image / Website', r'image|website|displayed'),
    ('Not Needed / Ordered By Mistake', r'mistake|wrong product ordered|not need|not required|does not want|better product'),
    ('Better Price Elsewhere', r'price'),
    ('Delivery Delayed', r'delay|late delivery'),
    ('Did Not Like The Product', r'not look good|not like'),
    ('Others', r'other|generic|thanos|^blank$|^$'),
]


def norm(e: pl.Expr) -> pl.Expr:
    """A key as text, outer spaces out, upper case (an empty cell is the text "NAN" / "NONE", as the old code had it)."""
    return e.cast(pl.Utf8).fill_null("nan").str.strip_chars().str.to_uppercase()


def _date(e: pl.Expr) -> pl.Expr:
    """A typed date of the master (Excel date read as text, or typed by hand)."""
    s = e.cast(pl.Utf8).str.strip_chars()
    return pl.coalesce(s.str.slice(0, 19).str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False, time_unit="us"),
                       s.str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us")),
                       s.str.to_date("%d-%m-%Y", strict=False).cast(pl.Datetime("us")),
                       s.str.to_date("%d/%m/%Y", strict=False).cast(pl.Datetime("us")))


def _mode(values: pl.Expr) -> pl.Expr:
    """The most common value; of equally common ones the smallest (pandas' mode()[0])."""
    return values.drop_nulls().mode().sort().first()


def load_master(supporting_dir):
    """(design_map: FINAL SKU -> DESIGN-NO, launch: Channel Name, FINAL SKU, date) from MasterSheet.xlsx."""
    from pathlib import Path

    from ..core import master_sheet as ms
    path = os.path.join(supporting_dir, 'MasterSheet.xlsx')
    log.info('Loading master: %s', path)
    m = ms.read(Path(path)).filter(pl.col('FINAL SKU').is_not_null())     # FINAL SKU = MASTER SKU
    design = (m.filter(pl.col('DESIGN-NO').is_not_null()).group_by('FINAL SKU').agg(_mode(pl.col('DESIGN-NO')).alias('d')))
    design_map = dict(zip(design['FINAL SKU'].to_list(), design['d'].to_list()))
    launch = (m.filter(pl.col('PORTAL LISTING DATE').is_not_null())
               .with_columns(date=_date(pl.col('PORTAL LISTING DATE')))
               .group_by('Channel Name', 'FINAL SKU').agg(pl.col('date').min()))
    return design_map, launch


def launch_dates(launch, portals) -> dict:
    """Earliest listing date of each FINAL SKU across the channels of one portal (or a list of portals)."""
    portals = [portals] if isinstance(portals, str) else portals
    channels = [c for p in portals for c in PORTAL_CHANNELS.get(p, [])]
    got = launch.filter(pl.col('Channel Name').is_in(channels)).group_by('FINAL SKU').agg(pl.col('date').min())
    return {k: v for k, v in zip(got['FINAL SKU'].to_list(), got['date'].to_list()) if v is not None}


def load_cost(supporting_dir) -> dict:
    """SKU (upper case) -> FINAL COST from Cost Sheet.xlsx; empty when the sheet is not there."""
    from ..core.tables import pnum, read_excel_text
    path = os.path.join(supporting_dir, 'Cost Sheet.xlsx')
    if not os.path.exists(path):
        log.warning('%s not found, COST will be blank', path)
        return {}
    log.info('Loading cost: %s', path)
    c = (read_excel_text(path, 0).select('SKU', cost=pnum(pl.col('FINAL COST')))
         .filter(pl.col('SKU').is_not_null() & pl.col('cost').is_not_null())
         .with_columns(k=norm(pl.col('SKU'))).unique('k', keep='first', maintain_order=True))
    return dict(zip(c['k'].to_list(), c['cost'].to_list()))


def cost_for(my_sku: pl.Expr, cost_map: dict) -> pl.Expr:
    """Cost Sheet is per style, so the SKU without its size first, then the whole SKU."""
    sku = my_sku.fill_null('').str.strip_chars().str.to_uppercase()
    style = sku.str.replace(r'-[^-]*$', '')
    look = lambda e: e.replace_strict(cost_map, default=None, return_dtype=pl.Float64) if cost_map else pl.lit(None, dtype=pl.Float64)  # noqa: E731
    return pl.coalesce(look(style), look(sku))


def clean_state(e: pl.Expr) -> pl.Expr:
    key = e.cast(pl.Utf8).fill_null('').str.strip_chars().str.to_uppercase()
    by_name = {name.upper(): name for name in STATE_ZONE}
    return pl.coalesce(key.replace_strict(STATE_ALIASES, default=None), key.replace_strict(by_name, default=None))


def merge_one(reason):
    text = ' '.join(str(reason).replace('_', ' ').lower().split())
    for group, pattern in REASON_GROUPS:
        if re.search(pattern, text):
            return group
    return reason


def finish(df: pl.DataFrame) -> pl.DataFrame:
    return df.select(COLUMNS).sort(['MY SKU', 'BRAND', 'ORDER STATUS'], nulls_last=True, maintain_order=True)


# ----------------------------------------------------------------------------- tables
def pct(part, whole, digits=2):
    return f'{(part / whole * 100 if whole else 0):.{digits}f}%'


def agg(df: pl.DataFrame, by) -> list[tuple]:
    """[(key, sales, returns, rate)] per group, keys A to Z (a key of several columns is a tuple)."""
    by = [by] if isinstance(by, str) else list(by)
    g = (df.filter(pl.all_horizontal([pl.col(c).is_not_null() for c in by]))
           .group_by(by).agg(pl.col('QTY').sum().alias('s'), pl.col('_ret').sum().alias('r')).sort(by))
    keys = g.select(by).rows() if len(by) > 1 else g[by[0]].to_list()
    return [(k, s, r, (r / s * 100) if s else 0.0) for k, s, r in zip(keys, g['s'].to_list(), g['r'].to_list())]


def top(rows: list[tuple], col: str, n=None) -> list[tuple]:
    """Highest first, ties in A-Z order (rows from agg(): col 'sales' or 'returns')."""
    i = {'sales': 1, 'returns': 2, 'qty': 1}[col]
    out = sorted(rows, key=lambda x: -x[i])            # stable: equal values stay A to Z
    return out if n is None else out[:n]


def reason_counts(df: pl.DataFrame) -> list[tuple[str, int]]:
    g = (df.filter((pl.col('ORDER STATUS') == 'Return') & pl.col('RETURN/EXCHANGE REASON').is_not_null())
           .group_by('RETURN/EXCHANGE REASON').agg(pl.col('QTY').sum().alias('q')).sort('RETURN/EXCHANGE REASON'))
    return [(r, q) for r, q, *_ in top(list(zip(g['RETURN/EXCHANGE REASON'].to_list(), g['q'].to_list())), 'qty')]


# ----------------------------------------------------------------------------- workbook
class Book:
    """xlsxwriter formats made once per look; Sheet writes cells 1-based, as the report's layout was drawn."""
    LOOK = {'summary_title': '#FAFD88', 'summary_head': '#E7FD88', 'blue_title': '#4F81BD', 'blue_section': '#D9E2F3',
            'blue_head': '#EEF4FB'}

    def __init__(self, path):
        import xlsxwriter
        self.wb = xlsxwriter.Workbook(path, {'strings_to_numbers': False, 'strings_to_formulas': False,
                                             'strings_to_urls': False})
        self._formats = {}

    def fmt(self, bold=False, size=None, color=None, fill=None, align=None, num=None, border=True):
        key = (bold, size, color, fill, align, num, border)
        if key not in self._formats:
            f = {}
            if border:
                f['border'] = 1
            if bold:
                f['bold'] = True
            if size:
                f['font_size'] = size
            if color:
                f['font_color'] = color
            if fill:
                f['bg_color'] = self.LOOK[fill]
                f['pattern'] = 1
            if align:
                f['align'] = align
            if num:
                f['num_format'] = num
            self._formats[key] = self.wb.add_format(f)
        return self._formats[key]


class Sheet:
    def __init__(self, book: Book, name: str):
        self.book, self.ws = book, book.wb.add_worksheet(name)
        self.max_row = 0

    def cell(self, row, col, value, bold=False, fill=None, align=None, fmt=None, size=None, color=None, border=True):
        f = self.book.fmt(bold, size, color, fill, align, fmt, border)
        r, c = row - 1, col - 1
        if value is None or value == '':                  # an empty text is an empty cell
            self.ws.write_blank(r, c, None, f)
        elif isinstance(value, str) and value.startswith('='):
            self.ws.write_formula(r, c, value, f)
        elif isinstance(value, str):
            self.ws.write_string(r, c, value, f)
        elif isinstance(value, datetime):
            self.ws.write_datetime(r, c, value, f)
        else:
            self.ws.write_number(r, c, value, f)
        self.max_row = max(self.max_row, row)

    def title(self, row, col, text, span, fill, align, bold=True, size=None, color=None):
        f = self.book.fmt(bold, size, color, fill, align, None, True)
        if span > 1:
            self.ws.merge_range(row - 1, col - 1, row - 1, col + span - 2, text, f)
        else:
            self.ws.write(row - 1, col - 1, text, f)
        self.max_row = max(self.max_row, row)

    def width(self, col, w):
        self.ws.set_column(col - 1, col - 1, w)

    def height(self, row, h):
        self.ws.set_row(row - 1, h)

    def line(self, row, col, values, bold=False):
        """Numbers right aligned "0", texts left, percentages (text) right."""
        for i, v in enumerate(values):
            if isinstance(v, str) and v.endswith('%'):
                self.cell(row, col + i, v, bold, align='right')
            elif isinstance(v, str):
                self.cell(row, col + i, v, bold, align='left')
            else:
                self.cell(row, col + i, v, bold, align='right', fmt='0')


def write_summary(sh: Sheet, df):
    def section(row, text, span, headers):
        sh.title(row, 1, text, span, 'summary_title', 'left')
        for i, h in enumerate(headers):
            sh.cell(row + 1, 1 + i, h, True, 'summary_head', 'left')
        return row + 2

    def line(row, values):
        for i, v in enumerate(values):
            sh.cell(row, 1 + i, v, align='left')

    sales, returns = int(df['QTY'].sum()), int(df['_ret'].sum())
    sh.title(1, 1, 'OVERALL METRICS', 2, 'summary_title', 'left')
    line(2, ['Total Sales Units', sales])
    line(3, ['Total Return Units', returns])
    line(4, ['Overall Return Rate (%)', pct(returns, sales)])

    row = section(6, 'BRAND WISE SUMMARY', 4, ['BRAND', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for brand, s, r, rate in agg(df, 'BRAND'):
        line(row, [brand, int(s), int(r), f'{rate:.2f}%'])
        row += 1

    row = section(row + 1, 'CATEGORY WISE SUMMARY', 4, ['CATEGORY', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for cat, s, r, rate in top(agg(df, 'CATEGORY'), 'sales'):
        line(row, [cat, int(s), int(r), f'{rate:.2f}%'])
        row += 1

    row = section(row + 1, 'TOP RETURN REASONS', 3, ['RETURN REASON', 'TOTAL QUANTITY', 'PERCENTAGE'])
    for reason, qty in reason_counts(df)[:20]:
        line(row, [reason, int(qty), pct(qty, returns)])
        row += 1

    skus = agg(df, 'MY SKU')
    row = section(row + 1, 'TOP SELLING SKUs', 4, ['MY SKU', 'SALES QUANTITY', 'RETURN QUANTITY', 'RETURN RATE (%)'])
    for sku, s, r, rate in top(skus, 'sales', 20):
        line(row, [sku, int(s), int(r), f'{rate:.2f}%'])
        row += 1

    row = section(row + 1, 'TOP RETURNED SKUs', 4, ['MY SKU', 'RETURN QUANTITY', 'SALES QUANTITY', 'RETURN RATE (%)'])
    for sku, s, r, rate in top(skus, 'returns', 20):
        line(row, [sku, int(r), int(s), f'{rate:.2f}%'])
        row += 1

    row = section(row + 1, 'MONTH WISE SUMMARY', 4, ['MONTH', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for month, s, r, rate in agg(df, '_month'):
        line(row, [month.strftime('%Y-%m'), int(s), int(r), f'{rate:.2f}%'])
        row += 1

    sh.width(1, 38)
    sh.width(2, 18.14)
    sh.width(4, 16.57)


def write_month_block(sh: Sheet, df, col, heading):
    def section(row, text, headers):
        sh.title(row, col, text, 4, 'blue_section', 'center')
        for i, h in enumerate(headers):
            sh.cell(row + 1, col + i, h, True, 'blue_head', 'center')
        return row + 2

    def line(row, values):
        sh.line(row, col, values)

    sh.title(1, col, heading, 4, 'blue_title', 'center', size=12, color='#FFFFFF')
    sales, returns = int(df['QTY'].sum()), int(df['_ret'].sum())
    sh.title(3, col, 'OVERALL METRICS', 4, 'blue_section', 'center')
    line(4, ['Total Sales Units', sales])
    line(5, ['Total Return Units', returns])
    line(6, ['Overall Return Rate (%)', pct(returns, sales)])

    row = section(8, 'STATUS WISE SUMMARY', ['STATUS', 'QTY', '%'])
    for status, qty in [('TOTAL', sales), ('Delivered', sales - returns), ('RETURN', returns), ('EXCHANGE', 0), ('RTO', 0)]:
        line(row, [status, qty, pct(qty, sales, 1)])
        row += 1

    row = section(row + 1, 'BRAND WISE SUMMARY', ['BRAND', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for brand, s, r, rate in top(agg(df, 'BRAND'), 'sales'):
        line(row, [brand, int(s), int(r), f'{rate:.2f}%'])
        row += 1

    row = section(row + 1, 'CATEGORY WISE SUMMARY', ['CATEGORY', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for cat, s, r, rate in top(agg(df, 'CATEGORY'), 'sales'):
        line(row, [cat, int(s), int(r), f'{rate:.2f}%'])
        row += 1

    skus = agg(df, 'MY SKU')
    row = section(row + 1, 'TOP SELLING SKUs', ['MY SKU', 'SALES QTY', 'RETURN QTY', 'RETURN RATE (%)'])
    for sku, s, r, rate in top(skus, 'sales', 10):
        line(row, [sku, int(s), int(r), f'{rate:.2f}%'])
        row += 1

    row = section(row + 1, 'TOP RETURNED SKUs', ['MY SKU', 'RETURN QTY', 'SALES QTY', 'RETURN RATE (%)'])
    for sku, s, r, rate in top(skus, 'returns', 10):
        line(row, [sku, int(r), int(s), f'{rate:.2f}%'])
        row += 1

    row = section(row + 1, 'TOP RETURN REASONS', ['ORDER STATUS', 'RETURN REASON', 'TOTAL QUANTITY', 'PERCENTAGE'])
    reasons = reason_counts(df)
    for reason, qty in reasons:
        line(row, ['RETURN', reason, int(qty), pct(qty, returns)])
        row += 1
    row += 1
    for status in ['EXCHANGE', 'RTO']:
        line(row, [status, 'No reasons', 0, '0.00%'])
        row += 1
    for reason, qty in reasons:
        line(row, ['ALL', reason, int(qty), pct(qty, returns)])
        row += 1

    for i, width in enumerate([24.71, 14.71]):
        sh.width(col + i, width)


def write_monthly_summary(sh: Sheet, df):
    months = sorted(df['_month'].unique().to_list())
    for i, month in enumerate(months):
        write_month_block(sh, df.filter(pl.col('_month') == month), 1 + 5 * i, f'MONTH: {month.strftime("%b-%Y").upper()}')
    write_month_block(sh, df, 1 + 5 * len(months), 'OVERALL')
    sh.height(1, 15.75)
    sh.ws.freeze_panes(1, 0)


def blue_section(sh: Sheet, row, text, headers):
    sh.title(row, 1, text, len(headers), 'blue_title', 'center', size=12, color='#FFFFFF')
    sh.height(row, 15.75)
    for i, h in enumerate(headers):
        sh.cell(row + 1, 1 + i, h, True, 'blue_section', 'center')
    return row + 2


def write_category_performance(sh: Sheet, df):
    sales, returns = int(df['QTY'].sum()), int(df['_ret'].sum())
    sh.title(1, 1, 'CATEGORY PERFORMANCE ANALYSIS', 6, 'blue_title', 'center', size=12, color='#FFFFFF')
    sh.height(1, 15.75)

    row = blue_section(sh, 4, 'OVERALL CATEGORY RANKING',
                       ['RANK', 'CATEGORY', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)', 'SALES SHARE (%)'])
    for rank, (cat, s, r, rate) in enumerate(top(agg(df, 'CATEGORY'), 'sales'), 1):
        sh.line(row, 1, [rank, cat, int(s), int(r), f'{rate:.2f}%', pct(s, sales)])
        row += 1

    row = blue_section(sh, row + 2, 'MONTH-WISE CATEGORY TREND',
                       ['MONTH', 'CATEGORY', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for month in sorted(df['_month'].unique().to_list()):
        for cat, s, r, rate in top(agg(df.filter(pl.col('_month') == month), 'CATEGORY'), 'sales'):
            sh.line(row, 1, [month.strftime('%b-%Y').upper(), cat, int(s), int(r), f'{rate:.2f}%'])
            row += 1

    row = blue_section(sh, row + 2, 'TOP RETURN REASONS BY CATEGORY',
                       ['CATEGORY', 'RETURN REASON', 'TOTAL QUANTITY', 'CATEGORY RETURN %', 'OVERALL RETURN %'])
    for cat in sorted(df['CATEGORY'].drop_nulls().unique().to_list()):
        reasons = reason_counts(df.filter(pl.col('CATEGORY') == cat))
        if not reasons:
            continue
        cat_returns = sum(q for _, q in reasons)
        for reason, qty in reasons[:5]:
            sh.line(row, 1, [cat, reason, int(qty), pct(qty, cat_returns), pct(qty, returns)])
            row += 1
        row += 1

    sh.width(1, 22.71)
    sh.width(3, 16.71)
    sh.ws.freeze_panes(1, 0)


def write_portal_wise(sh: Sheet, df):
    sales, returns = int(df['QTY'].sum()), int(df['_ret'].sum())
    portals = top(agg(df, 'PORTAL'), 'sales')
    names = [p for p, *_ in portals]

    row = blue_section(sh, 1, 'PORTAL WISE SALE RETURN', ['PORTAL', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)',
                                                           'SALES SHARE (%)', 'RETURN SHARE (%)'])
    for portal, s, r, rate in portals:
        sh.line(row, 1, [portal, int(s), int(r), f'{rate:.2f}%', pct(s, sales), pct(r, returns)])
        row += 1
    sh.line(row, 1, ['TOTAL', sales, returns, pct(returns, sales), '100.00%', '100.00%'], bold=True)
    row += 1

    row = blue_section(sh, row + 2, 'PORTAL WISE BRAND', ['PORTAL', 'BRAND', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for portal in names:
        for brand, s, r, rate in top(agg(df.filter(pl.col('PORTAL') == portal), 'BRAND'), 'sales'):
            sh.line(row, 1, [portal, brand, int(s), int(r), f'{rate:.2f}%'])
            row += 1

    row = blue_section(sh, row + 2, 'PORTAL WISE CATEGORY', ['PORTAL', 'CATEGORY', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for portal in names:
        for cat, s, r, rate in top(agg(df.filter(pl.col('PORTAL') == portal), 'CATEGORY'), 'sales'):
            sh.line(row, 1, [portal, cat, int(s), int(r), f'{rate:.2f}%'])
            row += 1

    row = blue_section(sh, row + 2, 'TOP RETURN REASONS BY PORTAL',
                       ['PORTAL', 'RETURN REASON', 'TOTAL QUANTITY', 'PORTAL RETURN %', 'OVERALL RETURN %'])
    for portal in names:
        reasons = reason_counts(df.filter(pl.col('PORTAL') == portal))
        total = sum(q for _, q in reasons)
        for reason, qty in reasons[:5]:
            sh.line(row, 1, [portal, reason, int(qty), pct(qty, total), pct(qty, returns)])
            row += 1
        if reasons:
            row += 1

    sh.width(1, 16)
    sh.width(2, 40)
    for col in range(3, 7):
        sh.width(col, 17)
    sh.ws.freeze_panes(1, 0)


def write_zone_wise(sh: Sheet, df):
    known = df.filter(pl.col('ZONE').is_not_null())
    sales, returns = int(known['QTY'].sum()), int(known['_ret'].sum())

    row = blue_section(sh, 1, 'ZONE WISE SALE RETURN', ['ZONE', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)',
                                                         'SALES SHARE (%)', 'RETURN SHARE (%)'])
    by_zone = {z: (s, r, rate) for z, s, r, rate in agg(known, 'ZONE')}
    for zone in ZONES:
        s, r, rate = by_zone.get(zone, (0, 0, 0.0))
        sh.line(row, 1, [zone, int(s), int(r), f'{rate:.2f}%', pct(s, sales), pct(r, returns)])
        row += 1
    sh.line(row, 1, ['TOTAL', sales, returns, pct(returns, sales), '100.00%', '100.00%'], bold=True)
    row += 1
    missing = int(df.filter(pl.col('ZONE').is_null())['QTY'].sum())
    if missing:
        sh.ws.write_string(row, 0, f'State not available in portal report: {missing} sales units not counted above')
        row += 1

    row = blue_section(sh, row + 2, 'ZONE WISE BRAND', ['ZONE', 'BRAND', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for zone in ZONES:
        for brand, s, r, rate in top(agg(known.filter(pl.col('ZONE') == zone), 'BRAND'), 'sales'):
            sh.line(row, 1, [zone, brand, int(s), int(r), f'{rate:.2f}%'])
            row += 1

    row = blue_section(sh, row + 2, 'ZONE WISE CATEGORY', ['ZONE', 'CATEGORY', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)'])
    for zone in ZONES:
        for cat, s, r, rate in top(agg(known.filter(pl.col('ZONE') == zone), 'CATEGORY'), 'sales'):
            sh.line(row, 1, [zone, cat, int(s), int(r), f'{rate:.2f}%'])
            row += 1

    row = blue_section(sh, row + 2, 'TOP RETURN REASONS BY ZONE',
                       ['ZONE', 'RETURN REASON', 'TOTAL QUANTITY', 'ZONE RETURN %', 'OVERALL RETURN %'])
    for zone in ZONES:
        reasons = reason_counts(known.filter(pl.col('ZONE') == zone))
        if not reasons:
            continue
        total = sum(q for _, q in reasons)
        for reason, qty in reasons[:5]:
            sh.line(row, 1, [zone, reason, int(qty), pct(qty, total), pct(qty, returns)])
            row += 1
        row += 1

    sh.width(1, 16)
    sh.width(2, 30)
    for col in range(3, 7):
        sh.width(col, 17)
    sh.ws.freeze_panes(1, 0)


def write_state_wise(sh: Sheet, df):
    sales, returns = int(df['QTY'].sum()), int(df['_ret'].sum())
    states = df.with_columns(pl.col('STATE').fill_null('NOT AVAILABLE'), pl.col('ZONE').fill_null('-'))

    row = blue_section(sh, 1, 'STATE WISE SALE RETURN', ['STATE', 'ZONE', 'SALES UNITS', 'RETURN UNITS', 'RETURN RATE (%)',
                                                          'SALES SHARE (%)', 'RETURN SHARE (%)'])
    g = top(agg(states, ['STATE', 'ZONE']), 'sales')
    g = [x for x in g if x[0][0] != 'NOT AVAILABLE'] + [x for x in g if x[0][0] == 'NOT AVAILABLE']   # unknown state last
    for (state, zone), s, r, rate in g:
        sh.line(row, 1, [state, zone, int(s), int(r), f'{rate:.2f}%', pct(s, sales), pct(r, returns)])
        row += 1
    sh.line(row, 1, ['TOTAL', '', sales, returns, pct(returns, sales), '100.00%', '100.00%'], bold=True)

    sh.width(1, 34)
    sh.width(2, 10)
    for col in range(3, 8):
        sh.width(col, 17)
    sh.ws.freeze_panes(2, 0)


def write_zone_mapping(sh: Sheet, df):
    aliases = {}
    for alias, state in STATE_ALIASES.items():
        aliases.setdefault(state, []).append(alias)

    row = blue_section(sh, 1, 'STATE TO ZONE MAPPING', ['ZONE', 'STATE', 'CODES / OTHER NAMES'])
    for zone in ZONES:
        for state in sorted(s for s, z in STATE_ZONE.items() if z == zone):
            sh.line(row, 1, [zone, state, ', '.join(aliases.get(state, []))])
            row += 1

    # Every state value exactly as the portal report wrote it, and where it landed
    row = blue_section(sh, row + 2, 'STATE VALUES IN THIS REPORT',
                       ['STATE IN PORTAL REPORT', 'MAPPED STATE', 'ZONE', 'SALES UNITS', 'RETURN UNITS'])
    raw = df.with_columns(pl.col('_raw_state').cast(pl.Utf8).fill_null('(blank)').str.strip_chars())
    first = {v: (s, z) for v, s, z in raw.unique('_raw_state', keep='first', maintain_order=True)
             .select('_raw_state', 'STATE', 'ZONE').iter_rows()}
    for value, s, r, _ in top(agg(raw, ['_raw_state']), 'sales'):
        state, zone = first[value]
        sh.line(row, 1, [value, 'NOT MAPPED' if state is None else state, '-' if zone is None else zone, int(s), int(r)])
        row += 1

    for col, w in ((1, 24), (2, 40), (3, 40), (4, 14), (5, 14)):
        sh.width(col, w)
    sh.ws.freeze_panes(2, 0)


def write_reason_mapping(sh: Sheet, df):
    ret = df.filter(pl.col('ORDER STATUS') == 'Return')
    returns = int(ret['QTY'].sum())
    counts = reason_counts(df)

    row = blue_section(sh, 1, 'MERGED RETURN REASONS', ['MERGED REASON', 'RETURN QTY', 'PERCENTAGE'])
    for reason, qty in counts:
        sh.line(row, 1, [reason, int(qty), pct(qty, returns)])
        row += 1

    # Every reason exactly as the portal report wrote it, and the group it was merged into
    row = blue_section(sh, row + 2, 'REASON VALUES IN THIS REPORT', ['MERGED REASON', 'REASON IN PORTAL REPORT', 'RETURN QTY'])
    order = {r: i for i, (r, _) in enumerate(counts)}
    g = (ret.filter(pl.col('RETURN/EXCHANGE REASON').is_not_null() & pl.col('_raw_reason').is_not_null())
            .group_by('RETURN/EXCHANGE REASON', '_raw_reason').agg(pl.col('QTY').sum()).sort('RETURN/EXCHANGE REASON', '_raw_reason'))
    rows = sorted(g.rows(), key=lambda x: (order[x[0]], -x[2]))
    for merged, raw_reason, qty in rows:
        sh.line(row, 1, [merged, raw_reason, int(qty)])
        row += 1

    for col, w in ((1, 44), (2, 50), (3, 14)):
        sh.width(col, w)
    sh.ws.freeze_panes(2, 0)


def write_sku_pivot(sh: Sheet, df, design_map: dict, launch_map: dict):
    from xlsxwriter.utility import xl_col_to_name
    g = df.group_by('MY SKU').agg(pl.col('QTY').sum().alias('sales'), pl.col('_ret').sum().alias('returns')).sort('MY SKU')
    ret = df.filter((pl.col('ORDER STATUS') == 'Return') & pl.col('RETURN/EXCHANGE REASON').is_not_null())
    reasons = sorted(ret['RETURN/EXCHANGE REASON'].unique().to_list())
    by = {(k, rs): q for k, rs, q in ret.group_by('MY SKU', 'RETURN/EXCHANGE REASON').agg(pl.col('QTY').sum()).iter_rows()}

    headers = ['MY SKU', 'DESIGN NO', 'PORTAL LAUNCH DATE', 'SALE UNIT', 'RETURN TOTAL', 'RETURN %'] + reasons
    ws, book = sh.ws, sh.book
    plain = None
    bold = book.fmt(bold=True, border=False)
    day = book.fmt(num='DD-MM-YYYY', border=False)
    two = book.fmt(num='0.00', border=False)
    for j, h in enumerate(headers):
        ws.write_string(1, j, h, bold)
    r = 2
    for sku, sales, returns in g.iter_rows():
        rate = round(returns / sales * 100 * 100) / 100 if sales else 0     # numpy's round(x, 2): half to even
        ws.write_string(r, 0, sku, plain)
        if design_map.get(sku) is not None:
            ws.write_string(r, 1, design_map[sku], plain)
        launch = launch_map.get(sku)
        if launch is not None:
            ws.write_datetime(r, 2, launch, day)
        else:
            ws.write_blank(r, 2, None, day)
        ws.write_number(r, 3, int(sales), plain)
        ws.write_number(r, 4, int(returns), plain)
        ws.write_number(r, 5, rate, two)
        for j, rs in enumerate(reasons, start=6):
            ws.write_number(r, j, int(by.get((sku, rs), 0)), plain)
        r += 1

    # Grand Total on top with SUBTOTAL(9, ...) so it follows the filter on the header row; each with its value (what a
    # preview that does not recalculate shows)
    from decimal import ROUND_HALF_UP, Decimal
    first, last = 3, max(r, 3)
    sales, returns = int(g['sales'].sum()), int(g['returns'].sum())
    totals = {4: sales, 5: returns, **{7 + j: int(sum(q for (_, x), q in by.items() if x == rs)) for j, rs in enumerate(reasons)}}
    rate = float(Decimal(repr(returns / sales * 100)).quantize(Decimal('0.01'), ROUND_HALF_UP)) if sales else 0   # Excel's ROUND
    ws.write_string(0, 0, 'Grand Total', bold)
    ws.write_blank(0, 1, None, bold)                  # the whole first row is bold, as before
    ws.write_blank(0, 2, None, bold)
    for col, value in totals.items():
        letter = xl_col_to_name(col - 1)
        ws.write_formula(0, col - 1, f'=SUBTOTAL(9,{letter}{first}:{letter}{last})', bold, value)
    ws.write_formula(0, 5, '=IFERROR(ROUND(E1/D1*100,2),0)', book.fmt(bold=True, num='0.00', border=False), rate)
    for col, w in ((1, 13), (2, 12), (3, 12), (6, 9.14)):
        sh.width(col, w)
    ws.autofilter(1, 0, last - 1, len(headers) - 1)
    ws.freeze_panes(2, 1)


def sheet_title(name, used):
    name = ''.join('_' if ch in '[]:*?/\\' else ch for ch in str(name))[:31] or 'Sheet'
    base, n = name, 2
    while name.lower() in used:
        name = f'{base[:28]}_{n}'
        n += 1
    used.add(name.lower())
    return name


def prepare(df: pl.DataFrame) -> pl.DataFrame:
    """The report's working columns: _ret, _month, the merged reason, the state and its zone."""
    is_ret = pl.col('ORDER STATUS') == 'Return'
    reasons = df.filter(is_ret)['RETURN/EXCHANGE REASON'].drop_nulls().unique().to_list()
    merged = {r: merge_one(r) for r in reasons}
    state = clean_state(pl.col('STATE'))
    return df.with_columns(
        pl.when(is_ret).then(pl.col('QTY')).otherwise(0).alias('_ret'),
        pl.col('MONTH').str.to_date('%m-%Y').cast(pl.Datetime('us')).alias('_month'),
        *[pl.col(c).fill_null('UNMAPPED') for c in ['BRAND', 'CATEGORY', 'MY SKU']],
        pl.col('RETURN/EXCHANGE REASON').alias('_raw_reason'),
        pl.when(is_ret).then(pl.col('RETURN/EXCHANGE REASON').replace_strict(merged, default=None, return_dtype=pl.Utf8))
          .otherwise(pl.col('RETURN/EXCHANGE REASON')).alias('RETURN/EXCHANGE REASON'),
        pl.col('STATE').alias('_raw_state'), state.alias('STATE'),
        state.replace_strict(STATE_ZONE, default=None).alias('ZONE'))


def write_report(df, portal, month_tag, out_root, design_map, launch_map):
    df = prepare(df)
    folder = os.path.join(out_root, 'Output', month_tag)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'{portal} SALE RETURN ANALYSIS {month_tag}.xlsx')
    book = Book(path)
    write_summary(Sheet(book, 'Summary'), df)
    write_monthly_summary(Sheet(book, 'Monthly Summary'), df)
    write_category_performance(Sheet(book, 'Category Performance'), df)
    used = {'summary', 'monthly summary', 'category performance', 'all brands', 'portal wise'}
    if df['PORTAL'].n_unique() > 1:
        write_portal_wise(Sheet(book, 'Portal Wise'), df)
    has_zone = bool(df['ZONE'].is_not_null().any())
    if has_zone:
        write_zone_wise(Sheet(book, 'Zone Wise'), df)
        write_state_wise(Sheet(book, 'State Wise'), df)
        used |= {'zone wise', 'state wise', 'zone mapping'}
    else:
        log.warning('%s report has no customer state, Zone Wise / State Wise sheets skipped', portal)
    write_sku_pivot(Sheet(book, 'All Brands'), df, design_map, launch_map)
    for brand in sorted(df['BRAND'].unique().to_list()):
        write_sku_pivot(Sheet(book, sheet_title(brand, used)), df.filter(pl.col('BRAND') == brand), design_map, launch_map)
    if has_zone:
        write_zone_mapping(Sheet(book, 'Zone Mapping'), df)
    write_reason_mapping(Sheet(book, sheet_title('Reason Mapping', used)), df)
    book.wb.close()
    return path


def write_template(df, portal, month_tag, out_root):
    folder = os.path.join(out_root, 'Template')
    os.makedirs(folder, exist_ok=True)
    final = finish(df)
    final.write_csv(os.path.join(folder, f'{portal} {month_tag} TEMPLATE.csv'))
    return final


def _month_tag(df) -> str:
    """The latest MONTH (MM-YYYY) as MON-YY, by date: "01-2027" sorts before "12-2026"."""
    return df['MONTH'].drop_nulls().str.to_date('%m-%Y').max().strftime('%b-%y').upper()


def write_combined(built, out_root, design_map, launch, tag=None):
    """MYNTRA COMBINED (Myntra MAIN + DBCC + FMCC) and ALL PORTAL reports from (portal, df, stats)
    parts; tag names the file (default: the latest month, MON-YY)."""
    results = []
    for name, parts in [('MYNTRA COMBINED', [b for b in built if b[0].startswith('MYNTRA')]), ('ALL PORTAL', built)]:
        if len(parts) < 2:
            continue
        df = pl.concat([part for _, part, _ in parts], how='diagonal_relaxed')
        # Same brand is spelt differently per portal (DressBerry / Dressberry, FASHFUN CLOTHING / FashFun):
        # use the most common spelling
        key = pl.col('BRAND').str.strip_chars().str.to_lowercase().replace(BRAND_ALIASES)
        best = df.select(key.alias('_k'), 'BRAND').group_by('_k').agg(_mode(pl.col('BRAND')).alias('_b'))
        df = (df.with_columns(key.alias('_k')).join(best, on='_k', how='left', maintain_order='left')
                .with_columns(pl.col('_b').alias('BRAND')).drop('_k', '_b'))
        month_tag = tag or _month_tag(df)
        launch_map = launch_dates(launch, [p for p, _, _ in parts])
        report = write_report(df, name, month_tag, out_root, design_map, launch_map)
        sold = int(df['QTY'].sum())
        returned = int(df.filter(pl.col('ORDER STATUS') == 'Return')['QTY'].sum())
        rate = returned / sold * 100 if sold else 0
        log.info('%s (%s) portals=%s sale qty=%d return qty=%d return %%=%.2f', name, month_tag,
                 ', '.join(p for p, _, _ in parts), sold, returned, rate)
        results.append({'portal': name, 'month': month_tag, 'sold': sold, 'returned': returned, 'rate': rate,
                        'report': report, 'template': None, 'stats': {}})
    return results


def read_data(path) -> pl.DataFrame:
    """A monthly data CSV (DATA_COLUMNS) back as the frame the builders made."""
    df = pl.read_csv(path, infer_schema=False)
    return df.with_columns(pl.col('QTY').cast(pl.Float64).cast(pl.Int64),
                           *[pl.col(c).cast(pl.Float64, strict=False) for c in ('SALE PRICE', 'COST') if c in df.columns])


def build_period(frames, tag, supporting_dir, out_root):
    """Reports over several months (e.g. a year) from the portals' monthly data:
    frames = {portal: df}. One report per portal plus the combined ones, all named with tag."""
    design_map, launch = load_master(supporting_dir)
    built = [(portal, df, {}) for portal, df in frames.items()]
    results = []
    for portal, df, _ in built:
        report = write_report(df, portal, tag, out_root, design_map, launch_dates(launch, portal))
        sold = int(df['QTY'].sum())
        returned = int(df.filter(pl.col('ORDER STATUS') == 'Return')['QTY'].sum())
        rate = returned / sold * 100 if sold else 0
        log.info('%s (%s) months=%s sale qty=%d return qty=%d return %%=%.2f', portal, tag,
                 sorted(df['MONTH'].drop_nulls().unique().to_list()), sold, returned, rate)
        results.append({'portal': portal, 'month': tag, 'sold': sold, 'returned': returned, 'rate': rate,
                        'report': report, 'template': None, 'stats': {}})
    return results + write_combined(built, out_root, design_map, launch, tag)


def month_date(text: str) -> date:
    """MM-YYYY -> its 1st."""
    return datetime.strptime(text, '%m-%Y').date()
