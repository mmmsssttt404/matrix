"""Real JEVDB integration and an explicitly separate, deterministic baseline."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
from uuid import uuid4

import pandas as pd
import pyarrow as pa

from .data import DataError, cutoff_utc


class ResearchUnavailable(RuntimeError):
    pass


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


_WORD = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[\u3400-\u9fff]+")
_PHRASE = re.compile(r'"([^"]+)"|“([^”]+)”')
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from",
    "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "our", "over",
    "such", "than", "that", "the", "their", "then", "these", "they", "this", "to",
    "under", "via", "was", "we", "were", "which", "with", "you", "your",
}


def _stem(token):
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text):
    """Case-fold, drop English stopwords, and use CJK bigrams for unspaced text."""
    text = str(text).casefold()
    tokens = []
    for match in _WORD.finditer(text):
        token = match.group(0)
        if (len(token) > 1 or token.isdigit()) and token not in _STOPWORDS:
            tokens.append(_stem(token))
    for sequence in _CJK.findall(text):
        if len(sequence) == 1:
            tokens.append(sequence)
        else:
            tokens.extend(sequence[i:i + 2] for i in range(len(sequence) - 1))
    return tokens


def parse_query(query):
    phrases = []
    for match in _PHRASE.finditer(query):
        phrase = (match.group(1) or match.group(2) or "").strip().casefold()
        if phrase:
            phrases.append(phrase)
    remainder = _PHRASE.sub(" ", query)
    terms = list(dict.fromkeys(tokenize(remainder)))
    return phrases, terms


def _bm25_scores(documents, terms, k1=1.5, b=0.75):
    tokenized = [tokenize(str(title) + " " + str(text))
                 for title, text in zip(documents.title, documents.text)]
    count = len(tokenized)
    average_length = sum(map(len, tokenized)) / count if count else 0.0
    frequencies = {}
    for tokens in tokenized:
        for term in set(tokens):
            frequencies[term] = frequencies.get(term, 0) + 1
    idf = {term: math.log(1 + (count - frequencies.get(term, 0) + 0.5)
                          / (frequencies.get(term, 0) + 0.5)) for term in terms}
    scores = []
    for tokens in tokenized:
        local = {}
        for token in tokens:
            local[token] = local.get(token, 0) + 1
        score = 0.0
        for term in terms:
            frequency = local.get(term, 0)
            if frequency and average_length:
                denominator = frequency + k1 * (1 - b + b * len(tokens) / average_length)
                score += idf[term] * frequency * (k1 + 1) / denominator
        scores.append(score)
    return scores


def _keyword_screen(eligible, query, operator):
    phrases, terms = parse_query(query)
    if not phrases and not terms:
        raise DataError("筛选条件至少需要一个检索词或短语。")
    texts = (eligible.title.astype(str) + " " + eligible.text.astype(str)).str.casefold()
    token_sets = [set(tokenize(text)) for text in texts]
    hits = [texts.str.contains(phrase, regex=False) for phrase in phrases]
    hits += [pd.Series([term in tokens for tokens in token_sets], index=eligible.index)
             for term in terms]
    if operator == "all":
        mask = pd.Series(True, index=eligible.index)
        for hit in hits:
            mask &= hit
    else:
        mask = pd.Series(False, index=eligible.index)
        for hit in hits:
            mask |= hit
    matched = eligible.loc[mask].copy()
    if matched.empty:
        return matched
    matched["match_score"] = _bm25_scores(matched, terms) if terms else 0.0
    if phrases:
        bonus = sum(texts.loc[matched.index].apply(lambda text: text.count(phrase))
                    for phrase in phrases)
        matched["match_score"] = matched["match_score"] + bonus.astype(float)
    matched["match_score"] = matched["match_score"].astype(float).round(6)
    return matched.sort_values(["match_score", "available_at"], ascending=[False, False]).reset_index(drop=True)


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
    operator: str = "all"

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (self.run_id + ".json")
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def frame(self):
        return pd.DataFrame(self.matches)


def inspect_backend():
    try:
        import jevdb
    except ImportError as exc:
        raise ResearchUnavailable("此平台没有JEVDB原生扩展；Windows桌面端可配置Linux语义服务地址。") from exc
    with jevdb.connect() as connection:
        functions = connection.execute("SELECT DISTINCT function_name FROM duckdb_functions() WHERE function_name LIKE 'jev_%' ORDER BY 1").fetchall()
        return {"jevdb": jevdb.__version__, "functions": [row[0] for row in functions]}


def screen(documents, query, asof, settings, mode="keyword", max_documents=100, operator="all"):
    query = query.strip()
    if not query or len(query) > 1000:
        raise DataError("筛选条件须为1—1000字符。")
    if not 1 <= max_documents <= 200:
        raise DataError("每次最多处理1—200条资料。")
    if operator not in {"all", "any"}:
        raise DataError("关键词匹配方式须为all或any。")
    eligible = documents.loc[documents.available_at < cutoff_utc(asof)].sort_values("available_at", ascending=False).head(max_documents).copy()
    if eligible.empty:
        raise DataError("研究日期之前没有可用资料；不能将当前公司简介当作历史资料。")
    start = time.perf_counter()
    stats = []
    if mode == "keyword":
        matches = _keyword_screen(eligible, query, operator)
        backend = "keyword_bm25"
    elif mode == "jevdb":
        if settings.service_url:
            return _remote_screen(eligible, query, asof, settings, max_documents, operator)
        if settings.backend not in {"jev", "llm"}:
            raise ResearchUnavailable("MATRIX_BACKEND须为jev或llm。")
        if not settings.credential_available:
            raise ResearchUnavailable("未配置模型API密钥。请在本地.env配置后重试，或明确选择离线关键词基线。")
        try:
            import jevdb
        except ImportError as exc:
            raise ResearchUnavailable("Windows语义查询需要Linux上的JEVDB服务，请在连接设置中填写地址；离线关键词模式可直接使用。") from exc
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
                       round(time.perf_counter() - start, 4), records, datetime.now(timezone.utc).isoformat(), stats, operator)


def _remote_screen(eligible, query, asof, settings, limit, operator="all"):
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen
    from uuid import UUID

    parsed = urlparse(settings.service_url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise ResearchUnavailable("远程语义服务须使用HTTPS；本机回环地址可使用HTTP。")
    if not settings.service_token:
        raise ResearchUnavailable("请配置语义服务访问令牌。")
    body = {"documents": json.loads(eligible.to_json(orient="records", date_format="iso")),
            "query": query, "asof": str(pd.Timestamp(asof).date()), "max_documents": limit,
            "operator": operator}
    request = Request(settings.service_url.rstrip("/") + "/research", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + settings.service_token})
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.load(response)
        run = ResearchRun(**payload)
        UUID(run.run_id)
        if run.query != query or run.asof != body["asof"] or not run.backend.startswith("jevdb_"):
            raise ValueError("Mismatched research response")
        if not {r["doc_id"] for r in run.matches} <= set(eligible.doc_id):
            raise ValueError("Unknown evidence returned by service")
        return run
    except Exception as exc:
        raise ResearchUnavailable("语义服务请求失败，请检查地址、令牌及服务端模型配置。没有返回替代语义结果。") from exc
