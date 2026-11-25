"""Files in replies and dynamic workings: the same for Telegram and the app (tools/files.py, tools/adhoc.py)."""
import base64
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from ultron.agents import chat
from ultron.core import attachments, config, http, sandbox
from ultron.integrations import telegram
from ultron.tools import adhoc, controls, files


def _file(tmp_path, name="x.png", size=10):
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return path


def test_attach_limits_and_take(tmp_path):
    attachments.start()
    assert "Attached" in attachments.attach(_file(tmp_path))
    assert "already" in attachments.attach(tmp_path / "x.png")
    big = _file(tmp_path, "big.xlsx", attachments.APP_MAX_BYTES + 1)
    assert "over the app's limit" in attachments.attach(big, app=True)
    assert "Attached" in attachments.attach(big)          # Telegram takes up to 50 MB
    for i in range(attachments.MAX_FILES - 2):
        attachments.attach(_file(tmp_path, f"{i}.csv"))
    assert "at most" in attachments.attach(_file(tmp_path, "extra.csv"))
    assert len(attachments.take()) == attachments.MAX_FILES
    assert attachments.take() == []


def test_sources_stay_inside_their_folder(tmp_path, monkeypatch):
    out = files.adhoc_root() / "0123456789ab" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "r.csv").write_text("a\n1\n")
    assert files.resolve("adhoc:0123456789ab/r.csv") == (out / "r.csv").resolve()
    for bad in ("adhoc:0123456789ab/../../x", "adhoc:../etc/passwd", "drive:x", "run:abc/x", "adhoc:0123456789ab/"):
        with pytest.raises(ValueError):
            files.resolve(bad)
    from ultron.integrations import github
    run_out = tmp_path / "run" / "output"
    (run_out / "vms").mkdir(parents=True)
    (run_out / "vms" / "NOV-26.png").write_bytes(b"png")
    monkeypatch.setattr(github, "output", lambda run_id: run_out)
    assert files.resolve("run:45631872650/vms/NOV-26.png").name == "NOV-26.png"
    with pytest.raises(ValueError):
        files.resolve("run:45631872650/../secret")


def test_send_file_labels_adhoc_and_uses_the_app_limit(tmp_path, monkeypatch):
    out = files.adhoc_root() / "abcdefabcdef" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "big.xlsx").write_bytes(b"x" * (attachments.APP_MAX_BYTES + 1))
    (out / "r.csv").write_text("a\n")
    attachments.start()
    token = controls.actor.set({"source": "job", "jobId": "j"})
    try:
        assert "limit" in files.send_file("adhoc:abcdefabcdef/big.xlsx")
    finally:
        controls.actor.reset(token)
    assert "Attached" in files.send_file("adhoc:abcdefabcdef/r.csv", "Returns by style")
    [item] = attachments.take()
    assert item.caption.startswith("Ad-hoc result, not a checked report.")


def test_deliver_sends_text_then_files(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text, chat=None: sent.append(("text", text, chat)) or True)
    monkeypatch.setattr(telegram, "send_file", lambda path, chat=None, caption="": sent.append(("file", path.name, chat)) or True)
    attachments.start()
    attachments.attach(_file(tmp_path), "ERP <vs> VMS")
    assert chat.deliver("answer", "42")
    assert sent == [("text", "answer", "42"), ("file", "x.png", "42")]


def test_app_reply_stores_files_before_the_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get", lambda: SimpleNamespace(worker=lambda: ("https://worker.test", "t")))
    monkeypatch.setattr(http, "get", lambda *a, **k: httpx.Response(200, json={"question": "q", "userId": "u"},
                                                                    request=httpx.Request("GET", "https://w")))
    def answer(question, conversation, **kw):
        attachments.attach(_file(tmp_path, "NOV-26.png", 3), "ERP vs VMS", app=True)
        return "Here it is"
    monkeypatch.setattr(chat, "answer", answer)
    calls = []
    def request(method, url, **kw):
        calls.append((url.rsplit("/", 1)[-1], kw["json"]))
        return httpx.Response(200, json={}, request=httpx.Request(method, url))
    monkeypatch.setattr(http, "request", request)
    assert chat.app_reply("00000000-0000-4000-8000-000000000002") == 0
    (first, upload), (_, done) = calls
    assert first == "file" and upload["name"] == "NOV-26.png" and upload["mime"] == "image/png"
    assert base64.b64decode(upload["data"]) == b"xxx"
    assert done["status"] == "completed"


def test_sandbox_line_locks_everything(tmp_path):
    line = sandbox.command("n", tmp_path / "job", tmp_path / "data", tmp_path / "out")
    joined = " ".join(line)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--user 65534:65534", "no-new-privileges",
                 "--pids-limit", "--memory", f"{tmp_path / 'data'}:/data:ro"):
        assert flag in joined
    assert "--env" in line and not any(a.startswith("--env-file") or a == "-e" for a in line)


def test_run_adhoc_says_why_it_cannot_run(monkeypatch):
    monkeypatch.setattr(sandbox, "unavailable", lambda: "Docker is not installed on this machine")
    assert "cannot run here: Docker" in adhoc.run_adhoc("print(1)")


def test_run_adhoc_rejects_unknown_sources(monkeypatch):
    monkeypatch.setattr(sandbox, "unavailable", lambda: "")
    assert "unknown data source" in adhoc.run_adhoc("print(1)", "http://x/y.csv")


def _docker_ready() -> bool:
    try:
        return sandbox.unavailable() == "" and subprocess.run(
            ["docker", "image", "inspect", sandbox.image()], capture_output=True, timeout=30).returncode == 0
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _docker_ready(), reason="needs Docker with the sandbox image")
def test_run_adhoc_end_to_end(tmp_path, monkeypatch):
    src = files.adhoc_root() / "fedcbafedcba" / "out"
    src.mkdir(parents=True, exist_ok=True)
    (src / "in.csv").write_text("style,qty\nA,2\nB,3\nA,1\n")
    script = """
import os, socket, polars as pl
df = pl.read_csv("/data/in.csv").group_by("style").agg(pl.col("qty").sum()).sort("style")
df.write_csv("/out/by_style.csv")
print(df)
print("secrets:", [k for k in os.environ if "TOKEN" in k or "KEY" in k])
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3); print("NET OPEN")
except OSError: print("no network")
"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "must-not-leak")
    text = adhoc.run_adhoc(script, "adhoc:fedcbafedcba/in.csv", "test")
    assert "Script finished" in text and "secrets: []" in text and "no network" in text
    assert "must-not-leak" not in text and "NET OPEN" not in text
    source = next(line.split()[0] for line in text.splitlines() if line.startswith("adhoc:"))
    assert files.resolve(source).read_text().splitlines() == ["style,qty", "A,3", "B,3"]
