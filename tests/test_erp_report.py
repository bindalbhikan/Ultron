"""ERP report(): asked again only while its count and rows disagree (6 Nov 2026: 522 rows of 521)."""
import pytest

from ultron.workings.portals import erp


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _client(answers):
    c = erp.Erp.__new__(erp.Erp)
    c.user_id, c.timeout = 1, 5
    c._fields = lambda rid: {"C1": "AWB"}
    seen = []

    class S:
        def get(self, url, params, timeout):
            seen.append(1)
            return answers[len(seen) - 1]
    c.s = S()
    return c, seen


def ok(n, total):
    return Resp(200, {"data": [{"C1": str(i)} for i in range(n)], "totalCount": total})


def test_count_mismatch_is_asked_again(monkeypatch):
    waits = []
    monkeypatch.setattr(erp.time, "sleep", waits.append)
    c, seen = _client([ok(3, 2), ok(2, 2)])
    assert [r["AWB"] for r in c.report(9, {"AWB": "AWB"})] == ["0", "1"]
    assert len(seen) == 2 and waits == [5]


def test_never_agreeing_fails_after_all_tries(monkeypatch):
    waits = []
    monkeypatch.setattr(erp.time, "sleep", waits.append)
    c, seen = _client([ok(3, 2)] * erp.COUNT_TRIES)
    with pytest.raises(erp.ErpError, match=f"3 rows came of 2 \\({erp.COUNT_TRIES} tries\\)"):
        c.report(9, {"AWB": "AWB"})
    assert len(seen) == erp.COUNT_TRIES and waits == [5 * n for n in range(1, erp.COUNT_TRIES)]


def test_http_error_and_bad_answer_are_not_asked_again(monkeypatch):
    monkeypatch.setattr(erp.time, "sleep", lambda s: None)
    c, seen = _client([Resp(500)])
    with pytest.raises(erp.ErpError, match="HTTP 500"):
        c.report(9, {"AWB": "AWB"})
    c, seen = _client([Resp(200, None)])
    with pytest.raises(erp.ErpError, match="no data in its answer"):
        c.report(9, {"AWB": "AWB"})
    assert len(seen) == 1
