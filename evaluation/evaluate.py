"""Evaluate the keyword baseline and JEVDB on a small hand-labeled set.

Relevance is defined at company (symbol) level, so the same labels can be used
with the bundled fixture or with a real data/documents.csv containing the same
companies. This is a course-project diagnostic, not investment advice.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matrixlab.config import Settings
from matrixlab.data import DataError, read_documents
from matrixlab.research import ResearchUnavailable, screen


def load_labels(path):
    frame = pd.read_csv(path)
    if not {"query", "relevant_symbols"} <= set(frame.columns):
        raise SystemExit("labels.csv 需要 query 与 relevant_symbols 两列")
    frame["relevant"] = frame.relevant_symbols.apply(
        lambda value: {item.strip().upper() for item in re.split(r"[;,]", str(value)) if item.strip()}
    )
    if frame.relevant.map(len).eq(0).any():
        raise SystemExit("每一条标注至少需要一个相关公司代码")
    return frame


def metrics(matched, relevant):
    matched = list(dict.fromkeys(matched))
    hits = [symbol for symbol in matched if symbol in relevant]
    true_positive = len(hits)
    precision = true_positive / len(matched) if matched else 0.0
    recall = true_positive / len(relevant) if relevant else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    reciprocal_rank = 0.0
    for rank, symbol in enumerate(matched, start=1):
        if symbol in relevant:
            reciprocal_rank = 1.0 / rank
            break
    return {
        "matched": matched,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "reciprocal_rank": round(reciprocal_rank, 4),
        "exact_match": set(matched) == relevant,
    }


def evaluate(name, documents, labels, settings, asof, operator, limit):
    rows = []
    for item in labels.itertuples(index=False):
        error = None
        try:
            run = screen(documents, item.query, asof, settings, name, limit, operator)
            matched = [record["symbol"] for record in run.matches]
        except (DataError, ResearchUnavailable) as exc:
            matched = []
            error = str(exc)
        row = {"query": item.query, "relevant": sorted(item.relevant),
               "notes": getattr(item, "notes", ""), "error": error}
        row.update(metrics(matched, item.relevant))
        rows.append(row)
    scored = [row for row in rows if not row["error"]]
    summary = {
        "queries": len(rows),
        "scored": len(scored),
        "errors": len(rows) - len(scored),
        "macro_precision": round(statistics.mean(row["precision"] for row in scored), 4) if scored else 0.0,
        "macro_recall": round(statistics.mean(row["recall"] for row in scored), 4) if scored else 0.0,
        "macro_f1": round(statistics.mean(row["f1"] for row in scored), 4) if scored else 0.0,
        "mrr": round(statistics.mean(row["reciprocal_rank"] for row in scored), 4) if scored else 0.0,
        "exact_match_rate": round(statistics.mean(row["exact_match"] for row in scored), 4) if scored else 0.0,
        "micro_precision": round(sum(len(set(row["matched"]) & set(row["relevant"])) for row in scored)
                                 / max(1, sum(len(set(row["matched"])) for row in scored)), 4),
        "micro_recall": round(sum(len(set(row["matched"]) & set(row["relevant"])) for row in scored)
                              / max(1, sum(len(set(row["relevant"])) for row in scored)), 4),
    }
    return {"mode": name, "operator": operator, "summary": summary, "queries": rows}


def main():
    parser = argparse.ArgumentParser(description="Evaluate keyword BM25 and JEVDB research modes")
    parser.add_argument("--documents", default=str(ROOT / "evaluation" / "documents.csv"))
    parser.add_argument("--labels", default=str(ROOT / "evaluation" / "labels.csv"))
    parser.add_argument("--asof", default="2026-11-25")
    parser.add_argument("--mode", choices=("keyword", "jevdb", "both"), default="keyword")
    parser.add_argument("--operator", choices=("all", "any"), default="all")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    documents = read_documents(args.documents)
    labels = load_labels(args.labels)
    settings = Settings.load()
    modes = ("keyword", "jevdb") if args.mode == "both" else (args.mode,)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asof": args.asof,
        "documents": str(Path(args.documents).resolve()),
        "labels": str(Path(args.labels).resolve()),
        "results": {},
    }
    for mode in modes:
        try:
            report["results"][mode] = evaluate(mode, documents, labels, settings, args.asof, args.operator, args.limit)
        except ResearchUnavailable as exc:
            report["results"][mode] = {"mode": mode, "summary": {"queries": len(labels), "errors": len(labels)},
                                       "error": str(exc), "queries": []}
        summary = report["results"][mode]["summary"]
        print(f"[{mode}] queries={summary['queries']} errors={summary.get('errors', 0)} "
              f"P={summary.get('macro_precision', 0):.3f} R={summary.get('macro_recall', 0):.3f} "
              f"F1={summary.get('macro_f1', 0):.3f} MRR={summary.get('mrr', 0):.3f}")
        result = report["results"][mode]
        if result.get("error"):
            print(f"  error: {result['error']}")
            continue
        for row in result["queries"]:
            flag = "OK " if row["f1"] >= 0.999 else "MISS"
            print(f"  {flag} {row['query']:<38} P={row['precision']:.2f} R={row['recall']:.2f} "
                  f"matched={','.join(row['matched']) or '-'} relevant={','.join(row['relevant'])}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = Path(args.output) if args.output else ROOT / "evaluation" / "results" / f"{args.mode}-{args.operator}-{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {output}")


if __name__ == "__main__":
    main()
