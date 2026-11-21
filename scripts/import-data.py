"""Import exported experiment data; never execute the source notebook."""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

source = Path(sys.argv[1])
target = Path(__file__).resolve().parents[1] / "public" / "data"
target.mkdir(parents=True, exist_ok=True)
def norm(value):
    return re.sub(r"\s+", " ", value).strip().lower()
def safe(value):
    return re.sub(r"(?i)(account\s*(?:number|no\.?)[^\n:]*[:\s]+)\d[\d -]{5,}", r"\1[REDACTED — CONFIRM WITH LIBRARY]", value)
records = {}
with (source / "all_source_faq_records.csv").open(encoding="utf-8-sig", newline="") as stream:
    for item in csv.DictReader(stream):
        uid = hashlib.sha1("|".join(norm(item[f]) for f in ["question", "option", "answer"]).encode()).hexdigest()[:16]
        if uid in records:
            records[uid]["source_refs"].append(item["source_ref"])
        else:
            records[uid] = {**{k: safe(v) for k, v in item.items()}, "id": uid, "source_refs": [item["source_ref"]]}
manifest = json.loads((source / "run_manifest.json").read_text(encoding="utf-8"))
assert len(records) == manifest["unique_records"], (len(records), manifest["unique_records"])
results = {}
for name in ["chunking_comparison", "difficulty_comparison", "per_question_retrieval_metrics", "human_answer_review"]:
    with (source / (name + ".csv")).open(encoding="utf-8-sig", newline="") as stream:
        results[name] = list(csv.DictReader(stream))
(target / "faqs.json").write_text(json.dumps(list(records.values()), ensure_ascii=False, indent=2), encoding="utf-8")
(target / "experiments.json").write_text(json.dumps({"manifest": manifest, **results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Imported {len(records)} unique FAQs, {len(manifest['worksheets'])} worksheets, and {len(results['chunking_comparison'])} experiment configurations.")
