"""OMSGuru order list: a line's channel id (found by pyright, 16 Nov 2026: a link in another shape crashed)."""
import pytest

from ultron.core.html import parse
from ultron.portals.omsguru_orders import channel_id


def _a(href):
    return parse(f'<a href="{href}">x</a>').select_one("a")


def test_channel_id_from_the_edit_link():
    assert channel_id(_a("/channel_companies/edit/57285")) == "57285"


def test_no_link_is_no_channel():
    assert channel_id(None) == ""


def test_a_link_in_another_shape_stops_with_a_clear_error():
    with pytest.raises(RuntimeError, match="has no channel id"):
        channel_id(_a("/channels/view/abc"))
