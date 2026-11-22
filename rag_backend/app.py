import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from flask import Flask, jsonify, request
from .core import ROOT, Config, SemanticIndex, extract_pdf, REFUSAL


def create_app(engine=None, generator=None, source=None):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    source = source or extract_pdf(Path(os.environ.get("RAG_PDF", ROOT / "public/data/library-faq.pdf")))
    config = Config(chunk_size=int(os.environ.get("RAG_CHUNK_SIZE", 1000)),
        chunk_overlap=int(os.environ.get("RAG_CHUNK_OVERLAP", 200)),
        top_k=int(os.environ.get("RAG_TOP_K", 3)), candidate_k=int(os.environ.get("RAG_CANDIDATE_K", 6)),
        device=os.environ.get("RAG_DEVICE", "cpu"))
    engine = engine or SemanticIndex(source["pages"], config)
    kind = os.environ.get("RAG_GENERATOR", "groq" if os.environ.get("GROQ_API_KEY") else "excerpts")
    if generator is None and kind == "groq":
        if not os.environ.get("GROQ_API_KEY"):
            raise ValueError("RAG_GENERATOR=groq requires GROQ_API_KEY.")
        from .generation import GroqGenerator
        generator = GroqGenerator(os.environ["GROQ_API_KEY"], os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"))
    elif generator is None and kind == "flan-t5":
        from .generation import FlanGenerator
        generator = FlanGenerator(config.device)
    elif generator is None and kind != "excerpts":
        raise ValueError("RAG_GENERATOR must be excerpts, groq, or flan-t5.")
    app = Flask(__name__, static_folder=str(ROOT / "public"), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 12000
    lock = threading.Lock()

    @app.before_request
    def authorize_api():
        # Required only for a separately hosted backend; local use needs no key.
        token = os.environ.get("RAG_BACKEND_TOKEN")
        if token and request.path.startswith("/api/"):
            import hmac
            if not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + token):
                return jsonify(error="Unauthorized backend request."), 401

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(ready=True, mode="faiss-" + kind, pages=len(source["pages"]),
            records=len(engine.chunks), chunks=len(engine.chunks), source=source["source_document"],
            sourceSha256=source["dataset_sha256"], embeddingModel=config.embedding_model,
            vectorStore="FAISS IndexFlatIP", chunkSize=config.chunk_size, overlap=config.chunk_overlap,
            topK=config.top_k, candidateK=config.candidate_k, notebook=True)

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("message"), str) or not data["message"].strip():
            return jsonify(error="Enter a nonempty question."), 400
        question = data["message"].strip()
        if len(question) > 1000:
            return jsonify(error="Keep questions under 1,000 characters."), 400
        started = time.perf_counter()
        # As in the notebook, each query is independent. Do not invent missing referents.
        try:
            with lock:
                sources = engine.sources(question, source["source_document"])
                result = {"status": "insufficient", "answer": REFUSAL, "citations": []}
                if sources and sources[0]["score"] >= float(os.environ.get("RAG_MIN_SIMILARITY", ".25")):
                    if generator is not None:
                        result = generator.answer(question, sources)
                    else:
                        result = {"status": "excerpts", "answer": "Retrieved PDF passage (not a generated answer):\n\n" + sources[0]["text"] + " [1]", "citations": []}
            ui_sources = [{"n": i, "id": s["source_id"], "ref": f"PDF page {s['page']} · chunk {s['chunk_id']}",
                           "page": s["page"], "chunk_id": s["chunk_id"], "score": round(s["score"], 4),
                           "text": s["text"], "question": f"PDF page {s['page']} · passage {s['chunk_id']}",
                           "document": source["source_document"]} for i, s in enumerate(sources, 1)]
            numbers = {s["id"]: s["n"] for s in ui_sources}
            answer = re.sub(r"\[(S\d+)\]", lambda m: f"[{numbers[m[1]]}]" if m[1] in numbers else m[0], result["answer"])
            if result["citations"]:
                answer += "\n\n" + " ".join(f"[{numbers[sid]}]" for sid in dict.fromkeys(c["source_id"] for c in result["citations"]))
            return jsonify(answer=answer, sources=ui_sources if result["status"] != "insufficient" else [],
                citations=result["citations"], status=result["status"], refused=result["status"] == "insufficient",
                mode="faiss-" + kind, elapsedMs=round((time.perf_counter() - started) * 1000),
                notice="FLAN-T5 baseline output is not verified by the Groq quote validator." if kind == "flan-t5" else None)
        except ValueError:
            app.logger.exception("Response failed format or evidence validation")
            return jsonify(error="The response failed the format or evidence checks. No generated answer was displayed."), 502
        except Exception:
            app.logger.exception("RAG request failed")
            return jsonify(error="The RAG request failed. Check the backend logs, model access, and provider configuration."), 502

    return app
