"""Read constants as data with AST; never execute notebook cells or outputs."""
import ast
import hashlib
import json
from pathlib import Path
import sys
from html.parser import HTMLParser

notebook = Path(sys.argv[1])
document = json.loads(notebook.read_text(encoding="utf-8"))
wanted = {"TEST_QUESTIONS", "EVAL_CONFIGS", "FAQ_SYSTEM_PROMPT", "FAQ_RESPONSE_SCHEMA"}
spec = {}
class SourceName(ast.NodeTransformer):
    def visit_Name(self, node):
        if node.id == "pdf_file":
            return ast.copy_location(ast.Constant("CONSOLIDATED FAQs for VLA - Basic information.pdf"), node)
        return node
for cell in document["cells"]:
    if cell["cell_type"] != "code":
        continue
    try:
        tree = ast.parse("".join(cell.get("source", [])))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                try:
                    value = ast.literal_eval(SourceName().visit(node.value))
                except (ValueError, TypeError):
                    continue
                if target.id not in spec:
                    spec[target.id] = value
if set(spec) != wanted:
    raise ValueError("The notebook is missing required constants.")
spec["provenance"] = {"notebook": notebook.name, "notebook_sha256": hashlib.sha256(notebook.read_bytes()).hexdigest()}
root = Path(__file__).resolve().parents[1]
(root / "rag_backend").mkdir(exist_ok=True)
(root / "rag_backend" / "notebook_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Imported {len(spec['TEST_QUESTIONS'])} evaluation questions, {len(spec['EVAL_CONFIGS'])} configurations and the notebook's evidence schema.")

class TableReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_cell = [], [], "", False
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row = []
        if tag in {"th", "td"}: self.cell, self.in_cell = "", True
    def handle_data(self, data):
        if self.in_cell: self.cell += data
    def handle_endtag(self, tag):
        if tag in {"th", "td"}: self.row.append(self.cell.strip()); self.in_cell = False
        if tag == "tr" and self.row: self.rows.append(self.row)

summary = None
for cell in document["cells"]:
    for output in cell.get("outputs", []):
        html = output.get("data", {}).get("text/html", "")
        html = "".join(html) if isinstance(html, list) else html
        if not html or "Indexing_Seconds" not in html or "Chunk_Size" not in html:
            continue
        parser = TableReader(); parser.feed(html)
        if parser.rows:
            headers = parser.rows[0]
            summary = [dict(zip(headers, row)) for row in parser.rows[1:] if len(row) == len(headers)]
            break
    if summary: break
if summary:
    if len(summary) != 12:
        raise ValueError("Expected 12 recorded configuration rows.")
    dataset = json.loads((root / "public/data/notebook-source.json").read_text(encoding="utf-8"))
    recorded = {"manifest": {"project": "PewPewPew PT-F2", "dataset": dataset["source_document"],
        "dataset_sha256": dataset["dataset_sha256"], "pages": 4, "chunks": 17,
        "active_config": "C12", "question_count": 9, "metric_basis": "reference_passage_provisional",
        "provenance": spec["provenance"], "recorded_not_rerun": True}, "chunking_comparison": [
        {"config": r["Config_ID"], "chunk_size": int(r["Chunk_Size"]), "overlap": int(r["Overlap"]),
         "top_k": 3, "chunks": int(r["Total_Chunks"]), "Precision@3": float(r["Precision@3"]),
         "Recall@3": float(r["Recall@3"]), "MRR@3": float(r["MRR@3"]),
         "indexing_s": float(r["Indexing_Seconds"])} for r in summary]}
    (root / "public/data/notebook-experiments.json").write_text(json.dumps(recorded, indent=2), encoding="utf-8")
    print("Imported 12 recorded, provisional result rows from notebook output; no benchmark was rerun.")
