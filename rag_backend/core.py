from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((Path(__file__).parent / "notebook_spec.json").read_text(encoding="utf-8"))
REFUSAL = "I could not confirm this from the supplied JRU Library FAQ passages. Please ask library staff."
CONFLICT = "The supplied FAQ passages contain conflicting guidance. Please ask library staff to confirm which applies."


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Config:
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 3
    candidate_k: int = 6
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"

    def __post_init__(self):
        if self.chunk_size <= 0 or not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("Require chunk_size > 0 and 0 <= chunk_overlap < chunk_size.")
        if self.top_k <= 0 or self.candidate_k < self.top_k:
            raise ValueError("Require 0 < top_k <= candidate_k.")


def extract_pdf(path: Path) -> dict:
    from pypdf import PdfReader
    pages = [{"page": i, "text": normalize(page.extract_text() or "")}
             for i, page in enumerate(PdfReader(path).pages, 1)]
    pages = [page for page in pages if page["text"]]
    if not pages:
        raise ValueError("PDF has no readable text; OCR is needed.")
    return {"source_document": path.name,
            "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "pages": pages}


def create_chunks(pages: list[dict], chunk_size=1000, chunk_overlap=200) -> list[dict]:
    Config(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = []
    for page in pages:
        for start in range(0, len(page["text"]), chunk_size - chunk_overlap):
            text = page["text"][start:start + chunk_size].strip()
            if text:
                chunks.append({"chunk_id": len(chunks), "page": page["page"], "text": text})
    return chunks


def validate_payload(payload: Any, sources: list[dict]) -> dict:
    """Notebook schema + verbatim evidence checks; these do not prove entailment."""
    if not isinstance(payload, dict) or set(payload) != {"status", "answer", "citations"}:
        raise ValueError("Unexpected response fields.")
    status = payload["status"]
    if status not in {"answered", "insufficient", "conflict"}:
        raise ValueError("Invalid response status.")
    if not isinstance(payload["answer"], str) or not payload["answer"].strip():
        raise ValueError("Empty answer.")
    if not isinstance(payload["citations"], list):
        raise ValueError("Citations must be a list.")
    lookup = {s["source_id"]: s for s in sources}
    checked = []
    for citation in payload["citations"]:
        if not isinstance(citation, dict) or set(citation) != {"source_id", "quote"}:
            raise ValueError("Invalid citation fields.")
        sid, quote = citation["source_id"], citation["quote"]
        if not isinstance(sid, str) or sid not in lookup:
            raise ValueError("Citation refers to an unavailable source.")
        if not isinstance(quote, str) or not normalize(quote) or normalize(quote) not in normalize(lookup[sid]["text"]):
            raise ValueError("Evidence quote does not match the source.")
        checked.append({**citation, "page": lookup[sid]["page"], "chunk_id": lookup[sid]["chunk_id"]})
    if status == "answered" and not checked:
        raise ValueError("An answered response requires evidence.")
    if status == "conflict" and len({normalize(c["quote"]) for c in checked}) < 2:
        raise ValueError("Conflict requires two distinct excerpts.")
    answer = REFUSAL if status == "insufficient" else CONFLICT if status == "conflict" else payload["answer"].strip()
    return {"status": status, "answer": answer, "citations": checked}


class SemanticIndex:
    def __init__(self, pages: list[dict], config: Config, encoder=None):
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
        self.config = config
        self.chunks = create_chunks(pages, config.chunk_size, config.chunk_overlap)
        if not self.chunks:
            raise ValueError("Cannot index an empty source.")
        self.encoder = encoder or SentenceTransformer(config.embedding_model, device=config.device,
            cache_folder=str(ROOT / ".model-cache"), trust_remote_code=False)
        embeddings = np.ascontiguousarray(self.encoder.encode(
            [chunk["text"] for chunk in self.chunks], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False), dtype="float32")
        if embeddings.shape[0] != len(self.chunks) or not np.isfinite(embeddings).all():
            raise ValueError("Invalid document embeddings.")
        if not np.allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-4):
            raise ValueError("Embedding normalization failed.")
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)
        if self.index.ntotal != len(self.chunks):
            raise ValueError("FAISS index count does not match source chunks.")

    def retrieve(self, question: str, top_k: int | None = None) -> list[dict]:
        import numpy as np
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Enter a nonempty question.")
        k = self.config.candidate_k if top_k is None else top_k
        if k <= 0:
            raise ValueError("top_k must be positive.")
        query = np.ascontiguousarray(self.encoder.encode([question], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False), dtype="float32")
        scores, indices = self.index.search(query, min(k, self.index.ntotal))
        return [{**self.chunks[int(idx)], "score": float(score), "rank": rank}
                for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), 1) if idx >= 0]

    def sources(self, question: str, document: str) -> list[dict]:
        seen, sources = set(), []
        for result in self.retrieve(question):
            key = normalize(result["text"])
            if key in seen:
                continue
            seen.add(key)
            sources.append({**result, "source_id": f"S{result['chunk_id']}", "source_document": document})
            if len(sources) == self.config.top_k:
                break
        return sources
