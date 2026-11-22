import json
import os
import re
import threading
from flask import Flask, jsonify, request
from .core import ROOT, Config, SemanticIndex, REFUSAL, basic_social_reply, clean_history, unsupported_request, looks_like_refusal, load_workbook_records, safe_excerpt


def create_app(engine=None, generator=None, source=None):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    if source is None:
        source = load_workbook_records(os.environ["RAG_WORKBOOK"]) if os.environ.get("RAG_WORKBOOK") else json.loads((ROOT / "server_data/faqs.json").read_text(encoding="utf-8"))
    config = Config(chunk_size=int(os.environ.get("RAG_CHUNK_SIZE", 800)), chunk_overlap=int(os.environ.get("RAG_CHUNK_OVERLAP", 100)),
        top_k=int(os.environ.get("RAG_TOP_K", 3)), device=os.environ.get("RAG_DEVICE", "cpu"), min_similarity=float(os.environ.get("RAG_MIN_SIMILARITY", .35)))
    engine = engine or SemanticIndex(source["records"], config)
    if generator is None and os.environ.get("GROQ_API_KEY"):
        from .generation import ConversationalGroq
        generator = ConversationalGroq(os.environ["GROQ_API_KEY"], os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"))
    app = Flask(__name__, static_folder=str(ROOT / "public"), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 16000
    lock = threading.Lock()
    records = {r["record_id"]: r for r in source["records"]}

    @app.before_request
    def authorize_api():
        token = os.environ.get("RAG_BACKEND_TOKEN")
        if token and request.path.startswith("/api/"):
            import hmac
            if not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + token):
                return jsonify(error="Unauthorized request."), 401

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/"): response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index(): return app.send_static_file("index.html")

    @app.get("/api/status")
    def status(): return jsonify(ready=True, service="Library-Assist")

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("message"), str) or not data["message"].strip():
            return jsonify(error="Please type a message first."), 400
        question = data["message"].strip()
        if len(question) > 1000: return jsonify(error="Keep questions under 1,000 characters."), 400
        history = clean_history(data.get("history"))
        social = basic_social_reply(question)
        if social: return jsonify(answer=social, refused=False)
        if unsupported_request(question): return jsonify(answer=REFUSAL, refused=True)
        try:
            with lock:
                query = generator.standalone_question(question, history) if generator else question
                if unsupported_request(query): return jsonify(answer=REFUSAL, refused=True)
                passages = engine.retrieve(query)
                if not passages or passages[0]["similarity"] < config.min_similarity:
                    return jsonify(answer=REFUSAL, refused=True)
                if generator:
                    answer = generator.answer(question, passages, history, query)
                else:
                    item = records.get(passages[0]["record_id"])
                    answer = (f"{item['option']}: " if item and item["option"] else "") + (item["answer"] if item else passages[0]["text"])
            citations = [int(m) for m in re.findall(r"\[(\d+)\]", answer)]
            if any(n < 1 or n > len(passages) for n in citations):
                raise ValueError("Invalid citation number")
            return jsonify(answer=safe_excerpt(answer), refused=looks_like_refusal(answer))
        except Exception:
            app.logger.exception("Conversational RAG failed")
            return jsonify(error="I couldn't complete that request. Please try again shortly."), 502

    return app
