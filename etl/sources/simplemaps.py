"""simplemaps US cities CSV source (no API)."""

from __future__ import annotations

import pandas as pd


def read_cities_csv(csv_path: str) -> pd.DataFrame:
    """Read the simplemaps uscities CSV into a DataFrame (raw columns).

    Column casting/selection happens in transforms.cities.
    """
    return pd.read_csv(csv_path)
