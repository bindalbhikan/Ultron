"""workings/core/tables.py (docs/CENTRALISE.md step 5): the same results as the code it replaces."""
import pandas as pd

from ultron.workings.core.tables import clean_id, col

IDS = ["19170.0", "19170", "98457588.0", "  32207.0 ", "50829", "100844482.0", "7", "0.0", "MURCC-DRESS-WV-B16"]


def test_clean_id_on_a_column_is_the_old_regex():
    s = pd.Series(IDS)
    assert clean_id(s).tolist() == s.astype(str).str.replace(r"\.0$", "", regex=True).tolist()


def test_clean_id_on_one_value_matches_the_old_replace_for_real_ids():
    for v in IDS:
        assert clean_id(v) == str(v).replace(".0", "").strip() or v == "0.0"   # "0.0": old gave "", new "0"
    assert clean_id(19170.0) == "19170" and clean_id(None) == "" and clean_id(float("nan")) == ""


def test_clean_id_keeps_a_missing_id_missing():
    """AJIO TAT normalize_master sets empty ids to None first: they must not become the text "None"."""
    s = pd.Series(["123.0", None, "45"], dtype=object)
    out = clean_id(s)
    assert out.tolist()[0] == "123" and out.tolist()[2] == "45" and out.isna().tolist() == [False, True, False]
    assert out.tolist() == s.str.replace(r"\.0$", "", regex=True).tolist()[:1] + [out.tolist()[1]] + ["45"]


def test_clean_id_only_cuts_the_end():
    assert clean_id("10.05") == "10.05"            # the old .replace(".0", "") made it "105"


def test_col_finds_a_column_whatever_its_case_and_is_empty_when_missing():
    df = pd.DataFrame({" Order Status ": [" C ", "F"], "x": [1, 2]})
    assert col(df, "order status").tolist() == ["C", "F"]
    missing = col(df, "warehouse_id")
    assert len(missing) == 0 or missing.isna().all()
