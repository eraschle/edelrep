# edelrep

Python-Projekt verwaltet mit [uv](https://github.com/astral-sh/uv).

## Voraussetzungen

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

## Entwicklung

Linting und Formatierung mit Ruff:

```bash
uv run ruff check .
uv run ruff format .
```

Type-Checking mit Pyright:

```bash
uv run pyright
```

## Ausführen

Ein CLI-Einstiegspunkt folgt in Phase 9. Vorerst:

```bash
uv run pytest
uv run pyright
```
