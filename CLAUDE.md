# Claude Code

@AGENTS.md

Claude-specific notes:
- Before every commit run `python scripts/docs/sync_docs.py` and commit what it changed together
  with your change (the Docs sync workflow catches it on push otherwise).
- At the end of a session, update the auto-memory notes too (open items, decisions, new facts).
- The "AI fix on failure" workflow (`.github/workflows/ci-fix.yml`) runs Claude Code in CI on a
  failed SPF run (Gemini CLI when Claude is not available); its task is `.github/ci-fix/prompt.md`,
  which points to AGENTS.md, and its PR includes the doc updates.
