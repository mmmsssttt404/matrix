"""Synthetic mathematical fixtures for tests only; never used by the application."""
import numpy as np
import pandas as pd
import pytest

from matrixlab.data import PRICE_BASIS, validate_documents, validate_prices


@pytest.fixture
def prices():
    rng = np.random.default_rng(7)
    days = pd.bdate_range("2024-01-02", periods=180)
    frames = []
    for i, symbol in enumerate(["AAA", "BBB", "CCC"]):
        close = (50 + 20 * i) * np.exp(np.cumsum(rng.normal(0.0002, 0.01 + i * .004, len(days))))
        opening = close * 0.997
        frames.append(pd.DataFrame({"date": days, "symbol": symbol, "open": opening,
                                    "high": close * 1.01, "low": opening * .99, "close": close,
                                    "volume": 1000, "price_basis": PRICE_BASIS,
                                    "source_url": "https://example.org/test-fixture",
                                    "retrieved_at": "2025-01-01T00:00:00Z"}))
    return validate_prices(pd.concat(frames, ignore_index=True))


@pytest.fixture
def documents():
    return validate_documents(pd.DataFrame([
        {"doc_id": "old", "symbol": "AAA", "title": "Cloud platform", "text": "cloud software",
         "available_at": "2024-01-02T12:00:00Z", "source_url": "https://example.org/old", "retrieved_at": "2025-01-01T00:00:00Z"},
        {"doc_id": "future", "symbol": "BBB", "title": "Cloud products", "text": "cloud software",
         "available_at": "2024-07-02T12:00:00Z", "source_url": "https://example.org/future", "retrieved_at": "2025-01-01T00:00:00Z"},
    ]))
