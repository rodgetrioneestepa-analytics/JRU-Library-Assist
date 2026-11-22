"""Bake the exact MiniLM encoder into the deployment image; never download at request time."""
import os
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu", trust_remote_code=False)
vector = model.encode("JRU Library", normalize_embeddings=True)
if vector.shape != (384,): raise RuntimeError("Unexpected MiniLM embedding dimension.")
model.save(os.environ.get("RAG_MODEL_PATH", "/opt/library-assist/model"))
print("Packaged sentence-transformers/all-MiniLM-L6-v2 for offline runtime loading.")
