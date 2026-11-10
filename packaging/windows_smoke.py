"""Test-only deterministic inputs for checking the frozen executable, never demo data."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from matrixlab.data import PRICE_BASIS

workspace = root / ".cache" / "windows-frozen-check"
workspace.mkdir(parents=True, exist_ok=True)
days = pd.bdate_range("2024-01-02", periods=180)
frames, docs = [], []
for number, symbol in enumerate(["TESTA", "TESTB"]):
    close = 50 * np.exp(np.cumsum(.001 + .01 * np.sin(np.arange(len(days)) / (3 + number))))
    frames.append(pd.DataFrame({"date": days, "symbol": symbol, "open": close * .999, "high": close * 1.01,
                                "low": close * .99, "close": close, "volume": 1000,
                                "price_basis": PRICE_BASIS, "source_url": "https://example.org/test-fixture",
                                "retrieved_at": "2025-01-01T00:00:00Z"}))
    docs.append({"doc_id": symbol, "symbol": symbol, "title": "Build check fixture", "text": "Deterministic test fixture only.",
                 "available_at": "2024-01-01T00:00:00Z", "retrieved_at": "2025-01-01T00:00:00Z", "source_url": "https://example.org/test-fixture"})
pd.concat(frames).to_csv(workspace / "prices.csv", index=False)
pd.DataFrame(docs).to_csv(workspace / "documents.csv", index=False)
executable = root / "dist" / "MatrixWorkbench" / ("MatrixWorkbench.exe" if sys.platform == "win32" else "MatrixWorkbench")
report = root / ".cache" / "frozen-check.json"
subprocess.run([str(executable), "--workspace", str(workspace), "--self-test-report", str(report)], check=True, timeout=90)
result = json.loads(report.read_text(encoding="utf-8"))
if result.get("ok") is not True:
    raise RuntimeError(result)
print(json.dumps(result))
