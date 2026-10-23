"""Real JEVDB integration and an explicitly separate, deterministic baseline."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

import jevdb
import pandas as pd
import pyarrow as pa

from .data import DataError, cutoff_utc


class ResearchUnavailable(RuntimeError):
    pass


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@dataclass
class ResearchRun:
    run_id: str
    backend: str
    query: str
    asof: str
    inputs: int
    elapsed_seconds: float
    matches: list
    created_at: str
    stats: list

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (self.run_id + ".json")
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def frame(self):
        return pd.DataFrame(self.matches)


def inspect_backend():
    with jevdb.connect() as connection:
        functions = connection.execute("SELECT DISTINCT function_name FROM duckdb_functions() WHERE function_name LIKE 'jev_%' ORDER BY 1").fetchall()
        return {"jevdb": jevdb.__version__, "functions": [row[0] for row in functions]}


def screen(documents, query, asof, settings, mode="keyword", max_documents=100):
    query = query.strip()
    if not query or len(query) > 1000:
        raise DataError("筛选条件须为1—1000字符。")
    if not 1 <= max_documents <= 200:
        raise DataError("每次最多处理1—200条资料。")
    eligible = documents.loc[documents.available_at < cutoff_utc(asof)].sort_values("available_at", ascending=False).head(max_documents).copy()
    if eligible.empty:
        raise DataError("研究日期之前没有可用资料；不能将当前公司简介当作历史资料。")
    start = time.perf_counter()
    stats = []
    if mode == "keyword":
        text = (eligible.title + " " + eligible.text).str.casefold()
        terms = query.casefold().split()
        mask = pd.Series(False, index=eligible.index)
        for term in terms:
            mask |= text.str.contains(term, regex=False)
        matches = eligible.loc[mask]
        backend = "keyword_baseline"
    elif mode == "jevdb":
        if settings.backend not in {"jev", "llm"}:
            raise ResearchUnavailable("MATRIX_BACKEND须为jev或llm。")
        if not settings.credential_available:
            raise ResearchUnavailable("未配置模型API密钥。请在本地.env配置后重试，或明确选择离线关键词基线。")
        if settings.backend == "llm" and (not settings.endpoint or not settings.model):
            raise ResearchUnavailable("兼容API还需要MATRIX_API_ENDPOINT与MATRIX_API_MODEL。")
        try:
            with jevdb.connect() as connection:
                connection.execute("SET threads=1")
                connection.execute("SET jevdb_threads=2")
                connection.execute("SET jevdb_timeout=30")
                connection.execute("SET jevdb_max_retries=1")
                secret = "jev (TYPE jev, PROVIDER env)" if settings.backend == "jev" else "llm (TYPE openai, PROVIDER env)"
                connection.execute("CREATE SECRET " + secret)
                connection.execute("SET jevdb_backend=" + _literal(settings.backend))
                if settings.endpoint:
                    connection.execute("SET jevdb_endpoint=" + _literal(settings.endpoint))
                if settings.model:
                    connection.execute("SET jevdb_model=" + _literal(settings.model))
                # DuckDB1.4.3 predates pandas3's native `str` dtype. Arrow avoids
                # that incompatible pandas scanner while retaining timestamps.
                connection.register("eligible_documents", pa.Table.from_pandas(eligible, preserve_index=False))
                # The condition is a quoted constant, never executable user-supplied SQL.
                matches = connection.execute(
                    "SELECT * FROM eligible_documents WHERE jev_holds("
                    + _literal(query) + ", {'title': title, 'text': text}) ORDER BY symbol, available_at"
                ).fetchdf()
                stats = connection.execute("SELECT * FROM jevdb_stats()").fetchdf().to_dict(orient="records")
        except Exception as exc:
            # Do not echo transport exceptions, which may include provider details.
            raise ResearchUnavailable("JEVDB查询失败；请检查本地凭证、网络及模型的结构化输出支持。未返回替代语义结果。") from exc
        backend = "jevdb_" + settings.backend
    else:
        raise DataError("未知研究模式。")
    records = json.loads(matches.to_json(orient="records", date_format="iso"))
    return ResearchRun(str(uuid4()), backend, query, str(pd.Timestamp(asof).date()), len(eligible),
                       round(time.perf_counter() - start, 4), records, datetime.now(timezone.utc).isoformat(), stats)
