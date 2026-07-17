"""Regressione sulla semantica temporale del lead/lag (correlation.py).

Storia: fino al 17/07 l'etichettatura del lag era invertita — uno scenario in cui
il social REAGISCE (volume il giorno dopo il movimento) produceva il picco sul
lato etichettato "anticipano". Trovato con lo scenario sintetico qui sotto in
fase di review. Questi test fissano la convenzione corretta:

    offset = giorno(volume) − giorno(movimento)
    offset < 0  -> il volume precede il movimento (social anticipa)
    offset = 0  -> stesso giorno
    offset > 0  -> il volume segue il movimento (social insegue)

I prezzi sono snapshot giornalieri stampati a mezzanotte UTC: il punto del
giorno t è il prezzo alla frontiera t-1/t, quindi la variazione fra gli snapshot
t-1 e t è il movimento avvenuto DURANTE il giorno t-1. La serie sintetica qui
riproduce esattamente questa convenzione: se i test passano, l'allineamento di
calendario è giusto end-to-end, non solo il segno dello shift.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from correlation import offset_profile  # noqa: E402

N_DAYS = 400
RNG = np.random.default_rng(7)


def synthetic(volume_offset: int) -> pd.DataFrame:
    """Serie giornaliera con movimenti nei giorni M e volume nei giorni M+offset.

    price[t] (snapshot stampato al giorno t) = chiusura del giorno t-1, come i
    dati reali midnight-stamped: un salto avvenuto nel giorno d compare nella
    differenza fra gli snapshot d e d+1.
    """
    move_days = np.zeros(N_DAYS, dtype=bool)
    move_days[RNG.choice(np.arange(20, N_DAYS - 20), size=40, replace=False)] = True
    jumps = np.where(move_days, 0.2, 0.0) + RNG.normal(0, 0.004, N_DAYS)

    price = 0.5 + np.concatenate([[0.0], np.cumsum(jumps)[:-1]])  # snapshot t = chiusura t-1
    volume = np.roll(move_days.astype(float) * 30, volume_offset) + RNG.poisson(1, N_DAYS)

    return pd.DataFrame({
        "day": pd.date_range("2025-01-01", periods=N_DAYS, freq="D"),
        "price": price,
        "volume": volume,
        "sentiment": 0.0,
    }).assign(price_delta=lambda d: d["price"].diff(),
              price_move=lambda d: d["price"].diff().abs())


@pytest.mark.parametrize("true_offset", [-2, -1, 0, 1, 2])
def test_peak_at_true_offset(true_offset):
    """Il profilo deve piccare esattamente all'offset con cui i dati sono costruiti."""
    g = synthetic(true_offset)
    prof = offset_profile(g["price_move"], g["volume"], max_lag=4, min_days=20)
    peak = max(prof, key=prof.get)
    assert peak == true_offset, (
        f"volume costruito a offset {true_offset:+d}, picco misurato a {peak:+d} "
        f"(profilo: { {k: round(v, 2) for k, v in prof.items()} })")


def test_reacting_social_is_labeled_as_following():
    """Il caso del bug originale: social che reagisce => lato POSITIVO del profilo."""
    g = synthetic(+1)
    prof = offset_profile(g["price_move"], g["volume"], max_lag=4, min_days=20)
    assert max(prof, key=prof.get) > 0


def test_flat_series_returns_nan():
    g = synthetic(0).assign(volume=1.0)
    prof = offset_profile(g["price_move"], g["volume"], max_lag=2, min_days=20)
    assert all(np.isnan(v) for v in prof.values())
