import logging
import os
import threading
import math
from flask import Flask, jsonify, request
from groq import RateLimitError
from .core import ROOT, SPEC, Config, SemanticIndex, resolve_source
from .generation import ConversationalGroq
from .service import ChatService


class Runtime:
    def __init__(self, engine=None, generator=None, source=None):
        self.engine, self.generator, self.source = engine, generator, source
        self.service = None
        self.lock = threading.Lock()

    def initialize(self):
        with self.lock:
            if self.service is not None: return self.service
            if self.generator is None:
                key = os.environ.get("GROQ_API_KEY", "").strip()
                if not key: raise RuntimeError("GROQ_API_KEY is not configured.")
                model = os.environ.get("GROQ_MODEL", SPEC["GROQ_MODEL"])
                if model != SPEC["GROQ_MODEL"]: raise RuntimeError("GROQ_MODEL differs from the reference notebook.")
                self.generator = ConversationalGroq(key, model)
            if self.engine is None:
                self.source = self.source or resolve_source()
                config = Config(chunk_size=int(os.environ.get("RAG_CHUNK_SIZE", 800)),
                    chunk_overlap=int(os.environ.get("RAG_CHUNK_OVERLAP", 100)), top_k=int(os.environ.get("RAG_TOP_K", 3)),
                    min_similarity=float(os.environ.get("RAG_MIN_SIMILARITY", .35)), device=os.environ.get("RAG_DEVICE", "cpu"))
                if (config.chunk_size, config.chunk_overlap, config.top_k, config.min_similarity) != (800, 100, 3, .35):
                    raise RuntimeError("Runtime settings differ from the notebook's active B configuration.")
                self.engine = SemanticIndex(self.source["records"], config, source_sha256=self.source["dataset_sha256"])
            self.service = ChatService(self.engine, self.generator)
            return self.service


def create_app(engine=None, generator=None, source=None):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    app = Flask(__name__, static_folder=str(ROOT / "public"), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 16000
    runtime = Runtime(engine, generator, source)
    app.extensions["rag_runtime"] = runtime

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
    def status():
        try:
            runtime.initialize()
            return jsonify(ready=True, service="Library-Assist", pipeline="minilm-chroma-groq",
                           index_fingerprint=getattr(runtime.engine, "fingerprint", "injected-test-engine"))
        except Exception as error:
            app.logger.error("RAG initialization failed (%s)", type(error).__name__)
            return jsonify(ready=False, service="Library-Assist", error="The library assistant is not ready. Please try again shortly."), 503

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("message"), str) or not data["message"].strip():
            return jsonify(error="Please type a message first."), 400
        question = data["message"].strip()
        if len(question) > 1000: return jsonify(error="Keep questions under 1,000 characters."), 400
        try:
            service = runtime.initialize()
            return jsonify(service.chat(question, data.get("history")))
        except RateLimitError as error:
            try: delay = max(1, math.ceil(float(error.response.headers.get("retry-after", "60"))))
            except (TypeError, ValueError, OverflowError): delay = 60
            app.logger.warning("Generation request rate limited; retry after %s seconds", delay)
            response = jsonify(error=f"The assistant has reached its request limit. Please try again in {delay} seconds.", retry_after_seconds=delay)
            response.headers['Retry-After'] = str(delay)
            return response, 429
        except ValueError:
            app.logger.exception("RAG response validation failed")
            return jsonify(error="I couldn't verify that response. Please try again."), 502
        except Exception as error:
            app.logger.error("RAG request failed (%s)", type(error).__name__)
            return jsonify(error="The library assistant is temporarily unavailable. Please try again shortly."), 503

    return app
