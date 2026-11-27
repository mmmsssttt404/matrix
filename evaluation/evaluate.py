"""Evaluate the keyword baseline, JEVDB operators, and Prune-First cascades
on the 40-query hand-labeled diagnostic set."""
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
from matrixlab.data import DataError, cutoff_utc, read_documents
from matrixlab.research import ResearchUnavailable, _prune_candidates, screen


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


def _summarize(rows):
    scored = [row for row in rows if not row["error"]]
    return {
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


def evaluate(name, documents, labels, settings, asof, operator, limit,
             jev_op="holds", threshold=0.5, prune_k=None):
    rows = []
    for item in labels.itertuples(index=False):
        error = None
        evaluated = None
        pruned_from = None
        try:
            run = screen(documents, item.query, asof, settings, name, limit, operator,
                         jev_op=jev_op, threshold=threshold, prune_k=prune_k)
            matched = [record["symbol"] for record in run.matches]
            evaluated = run.inputs
            pruned_from = run.pruned_from
        except (DataError, ResearchUnavailable) as exc:
            matched = []
            error = str(exc)
        row = {"query": item.query, "relevant": sorted(item.relevant),
               "notes": getattr(item, "notes", ""), "error": error,
               "inputs_evaluated": evaluated, "pruned_from": pruned_from}
        row.update(metrics(matched, item.relevant))
        rows.append(row)
    return {"mode": name, "operator": operator, "jev_op": jev_op,
            "summary": _summarize(rows), "queries": rows}


def prune_ablation(documents, labels, deepseek_results_path, asof="2026-11-25", ks=(3, 4, 6, 8, 12)):
    """Exact offline replay of Stage-1 BM25-OR pruning before Stage-2 DeepSeek JEVDB decisions.

    Applies the same asof cutoff and SQL ORDER BY symbol ordering as production screen().
    """
    eligible = documents.loc[documents.available_at < cutoff_utc(asof)].copy()
    if eligible.empty:
        raise SystemExit(f"asof={asof} 之前没有可用文档。")
    recorded = json.loads(Path(deepseek_results_path).read_text(encoding="utf-8"))
    jev_by_query = {row["query"]: set(row["matched"]) for row in recorded["results"]["jevdb"]["queries"]}
    total_docs = len(eligible)
    table = []
    for k in ks:
        rows = []
        total_eval = 0
        fallback_count = 0
        for item in labels.itertuples(index=False):
            shortlist, fell_back = _prune_candidates(eligible, item.query, k)
            fallback_count += int(fell_back)
            total_eval += len(shortlist)
            # Mirror SQL ORDER BY symbol, available_at in production screen().
            surviving = sorted({s for s in shortlist["symbol"].tolist() if s in jev_by_query.get(item.query, set())})
            row = {"query": item.query, "relevant": sorted(item.relevant), "error": None,
                   "candidates_sent": len(shortlist), "fallback": fell_back}
            row.update(metrics(surviving, item.relevant))
            rows.append(row)
        summary = _summarize(rows)
        total_possible = len(labels) * total_docs
        summary["prune_k"] = k
        summary["total_docs_evaluated"] = total_eval
        summary["total_possible_docs"] = total_possible
        summary["docs_pruned_ratio"] = round(1.0 - total_eval / total_possible, 4)
        summary["fallback_queries"] = fallback_count
        table.append({"prune_k": k, "summary": summary, "queries": rows})
    return table


def main():
    parser = argparse.ArgumentParser(description="Evaluate keyword BM25, JEVDB, and Prune-First modes")
    parser.add_argument("--documents", default=str(ROOT / "evaluation" / "documents.csv"))
    parser.add_argument("--labels", default=str(ROOT / "evaluation" / "labels.csv"))
    parser.add_argument("--asof", default="2026-11-25")
    parser.add_argument("--mode", choices=("keyword", "jevdb", "both", "prune_ablation"), default="keyword")
    parser.add_argument("--operator", choices=("all", "any"), default="all")
    parser.add_argument("--jev-op", choices=("holds", "probability", "choose", "score", "prune_then_decide"), default="holds")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--prune-k", type=int, default=None)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--recorded-jevdb", default=str(ROOT / "evaluation" / "results" / "both-deepseek.json"))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    documents = read_documents(args.documents)
    labels = load_labels(args.labels)
    if args.mode == "prune_ablation":
        ablation = prune_ablation(documents, labels, args.recorded_jevdb, asof=args.asof)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "asof": args.asof,
            "mode": "prune_ablation",
            "source_jevdb_results": str(Path(args.recorded_jevdb).name),
            "ablation": ablation,
        }
        for entry in ablation:
            s = entry["summary"]
            print(f"[prune_k={s['prune_k']:>2}] pruned={s['docs_pruned_ratio']:.1%} eval_docs={s['total_docs_evaluated']:>3}/{s['total_possible_docs']} "
                  f"fallbacks={s['fallback_queries']:>2} P={s['macro_precision']:.3f} R={s['macro_recall']:.3f} "
                  f"F1={s['macro_f1']:.3f} EM={s['exact_match_rate']:.3f}")
        output = Path(args.output) if args.output else ROOT / "evaluation" / "results" / "prune-ablation.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved {output}")
        return

    def _rel(path_str):
        p = Path(path_str).resolve()
        try:
            return str(p.relative_to(ROOT))
        except ValueError:
            return str(p)

    settings = Settings.load()
    modes = ("keyword", "jevdb") if args.mode == "both" else (args.mode,)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asof": args.asof,
        "documents": _rel(args.documents),
        "labels": _rel(args.labels),
        "results": {},
    }
    for mode in modes:
        try:
            report["results"][mode] = evaluate(
                mode, documents, labels, settings, args.asof, args.operator, args.limit,
                jev_op=args.jev_op, threshold=args.threshold, prune_k=args.prune_k,
            )
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
