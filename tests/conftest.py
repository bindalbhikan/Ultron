"""Tests write their results into a folder of their own, never the user's data folder (ultron/core/paths.py)."""
import os
import tempfile

os.environ.setdefault("ULTRON_OUTPUT", tempfile.mkdtemp(prefix="ultron_test_output_"))
