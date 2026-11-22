"""Rerun notebook retrieval measurements; writes actual results, never expected timings."""
import argparse
import json
from pathlib import Path
import time
from .core import ROOT, SPEC, Config, SemanticIndex, extract_pdf, normalize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=ROOT / "public/data/library-faq.pdf")
    parser.add_argument("--output", type=Path, default=ROOT / ".rag-results/retrieval-evaluation.json")
    args = parser.parse_args()
    source = extract_pdf(args.pdf)
    pages = {p["page"]: normalize(p["text"]) for p in source["pages"]}
    for question in SPEC["TEST_QUESTIONS"]:
        for evidence in question["evidence"]:
            if normalize(evidence["passage"]) not in pages.get(evidence["page"], ""):
                raise ValueError(f"Evidence for {question['id']} is absent from the supplied PDF.")
    summaries, details, encoder = [], [], None
    for config in SPEC["EVAL_CONFIGS"]:
        started = time.perf_counter()
        index = SemanticIndex(source["pages"], Config(chunk_size=config["chunk_size"], chunk_overlap=config["chunk_overlap"]), encoder)
        elapsed = time.perf_counter() - started
        encoder = index.encoder
        rows = []
        for question in SPEC["TEST_QUESTIONS"]:
            retrieved = index.retrieve(question["question"], 3)
            units = [{i for i, evidence in enumerate(question["evidence"])
                      if evidence["page"] == chunk["page"] and normalize(evidence["passage"]) in normalize(chunk["text"])} for chunk in retrieved]
            first = next((i for i, unit in enumerate(units, 1) if unit), None)
            row = {"config": config["config_id"], "question_id": question["id"], "difficulty": question["difficulty"],
                "Precision@3": sum(bool(unit) for unit in units) / 3,
                "Recall@3": len(set().union(*units)) / len(question["evidence"]), "MRR@3": 1 / first if first else 0,
                "retrieved": retrieved}
            rows.append(row); details.append(row)
        summaries.append({"config": config["config_id"], "chunk_size": config["chunk_size"], "overlap": config["chunk_overlap"],
            "top_k": 3, "chunks": len(index.chunks), "indexing_s": elapsed,
            **{metric: sum(row[metric] for row in rows) / len(rows) for metric in ["Precision@3", "Recall@3", "MRR@3"]}})
        print(config["config_id"], "completed", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"dataset_sha256": source["dataset_sha256"], "metric_basis": "reference_passage_provisional",
        "recorded_not_rerun": False, "chunking_comparison": summaries, "per_question": details}, indent=2), encoding="utf-8")
    print("Saved actual retrieval measurements:", args.output)


if __name__ == "__main__": main()
