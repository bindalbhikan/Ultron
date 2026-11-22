"""workings/core/tables.py (docs/CENTRALISE.md step 5): ids and columns of report files."""
import polars as pl

from ultron.workings.core.tables import clean_id, pclean_id, pcol

IDS = ["19170.0", "19170", "98457588.0", "  32207.0 ", "50829", "100844482.0", "7", "0.0", "MURCC-DRESS-WV-B16"]


def test_pclean_id_cuts_only_a_trailing_zero_decimal():
    got = pl.DataFrame({"i": IDS}).select(pclean_id(pl.col("i")))["i"].to_list()
    assert got == ["19170", "19170", "98457588", "  32207.0 ", "50829", "100844482", "7", "0", "MURCC-DRESS-WV-B16"]


def test_clean_id_on_one_value():
    assert [clean_id(v) for v in IDS] == ["19170", "19170", "98457588", "32207", "50829", "100844482", "7", "0", "MURCC-DRESS-WV-B16"]
    assert clean_id(19170.0) == "19170" and clean_id(None) == "" and clean_id(float("nan")) == ""


def test_a_missing_id_stays_missing():
    """AJIO TAT normalize_master: empty ids must not become the text "None"."""
    got = pl.DataFrame({"i": ["123.0", None, "45"]}).select(pclean_id(pl.col("i")))["i"].to_list()
    assert got == ["123", None, "45"]


def test_clean_id_only_cuts_the_end():
    assert clean_id("10.05") == "10.05"            # the old .replace(".0", "") made it "105"


def test_pcol_finds_a_column_whatever_its_case_and_is_empty_when_missing():
    df = pl.DataFrame({" Order Status ": [" C ", "F"], "x": [1, 2]})
    assert df.select(pcol(df, "order status"))[" Order Status "].to_list() == ["C", "F"]
    assert df.with_columns(pcol(df, "warehouse_id").alias("w"))["w"].to_list() == [None, None]
