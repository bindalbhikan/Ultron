"""The morning / evening phone tables (28 wide): the change column never runs into the number before it."""
from ultron.workings.morning.pipeline import change, change_cell


def test_change_cell_fits_four_characters():
    assert change(100, 24) == "+317%"                 # the percent stays for the weekly / MIS tables
    assert change_cell(100, 24) == "4.2x"             # was "24+317%" in the evening table, 23 Nov 2026
    assert change_cell(2, 1) == "2.0x"
    assert change_cell(150, 10) == "15x"
    assert change_cell(5000, 1) == "999x"
    assert [change_cell(*p) for p in ((71, 69), (4, 9), (21, 21), (1, 0), (0, 0))] == ["+3%", "-56%", "+0%", "new", "-"]
    for now, before in ((100, 24), (99, 50), (0, 7), (12345, 1)):
        assert len(change_cell(now, before)) <= 4
