import os
from .app import create_app

app = create_app()
port = int(os.environ.get("RAG_PORT", "5000"))
print(f"Notebook FAISS RAG: http://127.0.0.1:{port}", flush=True)
app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
