"""Baseline della dashboard: ogni view deve renderizzare senza eccezioni.

Non testa l'estetica: testa che la demo live non possa esplodere aprendo una
view. Gira sull'intero dataset processed (nessun mock): se un parquet manca o
uno schema cambia, fallisce qui e non davanti alla commissione.

Uso:  python3 -m pytest tests/test_dashboard.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
VIEWS = [
    "1 · Contratti (Task 2.1)",
    "2 · Discorso social (Task 2.2)",
    "3 · Segnale ↔ mercato (Task 2.3)",
    "4 · Confronto piattaforme (Task 2.4)",
    "5 · Predizione (Task 3)",
    "🔎 Esplora i post",
]


def _run(view: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value(view).run()
    return at


@pytest.mark.parametrize("view", VIEWS)
def test_view_renders(view: str) -> None:
    at = _run(view)
    assert not at.exception, f"{view}: {[e.value for e in at.exception]}"


def test_filters_do_not_break() -> None:
    """Dominio singolo + esito filtrato: il percorso che una demo tocca di sicuro."""
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value(VIEWS[3]).run()
    at.sidebar.multiselect[0].set_value(["sports"]).run()
    at.sidebar.selectbox[0].set_value("Yes").run()
    assert not at.exception, [e.value for e in at.exception]
