---
name: python-preferences
description: Gives preferences for python. Use before writing or executing python.
---

- use `uv` to manage python environments and pin versions
- each python project gets its own `.venv`; don't share venvs unless asked
- use Google style docstrings on all public methods / classes
- pydantic preferred
- organize tests into `tests/{unit,integration,e2e}`