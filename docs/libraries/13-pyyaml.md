# 13. PyYAML for the shared action catalog

Status: added 25 Nov 2026, PyYAML 6.0.4 locked by uv.
It reads GitHub workflow input declarations structurally, avoiding regex parsing or hand-copied form metadata.
The generator uses the safe LibYAML loader when available and PyYAML's supported pure Python safe loader elsewhere.
The MIT licence permits commercial use. It does not execute arbitrary YAML tags.
Existing ruff, pytest and pyright tooling is now declared in the development group so local checks survive a frozen sync; CI bot exports exclude that group.
Validation covers registry freshness, workflow input parity and every Telegram command/scheduled input.
No report calculations or saved values are changed by YAML parsing.

[PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation)
