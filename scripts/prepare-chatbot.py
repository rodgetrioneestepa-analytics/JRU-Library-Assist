"""Import the corrected notebook's constants and workbook without executing cells."""
import ast
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
notebook, workbook = map(Path, sys.argv[1:3])
document = json.loads(notebook.read_text(encoding="utf-8"))
trees = [ast.parse("".join(c["source"])) for c in document["cells"] if c["cell_type"] == "code" and not "".join(c["source"]).lstrip().startswith("%")]
constants = {}
wanted = {"CONFIGS", "ACTIVE_CONFIG", "MIN_SIMILARITY", "EMBEDDING_MODEL", "GROQ_MODEL", "MAX_HISTORY_MESSAGES", "REFUSAL"}
for tree in trees:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    constants[target.id] = ast.literal_eval(node.value)

def string_value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
    if isinstance(node, ast.Name) and node.id == "REFUSAL": return constants["REFUSAL"]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add): return string_value(node.left) + string_value(node.right)
    raise ValueError("Unexpected prompt expression.")

for tree in trees:
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef): continue
        variable = "system" if function.name == "answer_question" else "instructions" if function.name == "standalone_search_question" else None
        if variable:
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in node.targets):
                    constants["ANSWER_PROMPT" if variable == "system" else "REWRITE_PROMPT"] = string_value(node.value)
if not wanted.issubset(constants) or not {"ANSWER_PROMPT", "REWRITE_PROMPT"}.issubset(constants):
    raise ValueError("The corrected notebook is missing a required setting or prompt.")
constants["provenance"] = {"notebook": notebook.name, "sha256": hashlib.sha256(notebook.read_bytes()).hexdigest()}
(root / "rag_backend/notebook_spec.json").write_text(json.dumps(constants, ensure_ascii=False, indent=2), encoding="utf-8")
sys.path.insert(0, str(root))
from rag_backend.core import load_workbook_records
source = load_workbook_records(workbook)
(root / "server_data").mkdir(exist_ok=True)
(root / "server_data/faqs.json").write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Prepared {len(source['records'])} FAQ records from {len(source['worksheets'])} sheets using the corrected notebook's parsing rules.")
print("Content is stored outside the website's public directory.")
