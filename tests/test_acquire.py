from matrixlab.acquire import fetch_dataset
from matrixlab.data import read_documents


def test_refresh_keeps_previously_imported_documents(prices, documents, tmp_path, monkeypatch):
    from matrixlab import acquire

    documents.iloc[[0]].to_csv(tmp_path / "documents.csv", index=False)
    new = documents.iloc[1].to_dict()
    monkeypatch.setattr(acquire, "download_history", lambda symbol, start, end: prices.loc[prices.symbol.eq(symbol)])
    monkeypatch.setattr(acquire, "download_profile", lambda symbol: new)
    fetch_dataset(tmp_path, ["AAA"])
    assert set(read_documents(tmp_path / "documents.csv").doc_id) == {"old", "future"}
