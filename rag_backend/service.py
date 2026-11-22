"""The shared notebook chat-turn path; no lexical or stored-answer fallback."""
import re
import threading
import time
from .core import REFUSAL, SPEC, basic_social_reply, clean_history, unsupported_request, looks_like_refusal, safe_excerpt


class ChatService:
    def __init__(self, engine, generator):
        self.engine, self.generator = engine, generator
        self._retrieval_lock = threading.Lock()

    def chat(self, question, history=None):
        question = str(question).strip()
        history = clean_history(history)
        social = basic_social_reply(question)
        if social:
            return {"question": question, "retrieval_query": "", "answer": social, "sources": [], "refused": False,
                    "retrieval": [], "retrieval_s": 0.0, "generation_s": 0.0}
        query = self.generator.standalone_question(question, history)
        base = {"question": question, "retrieval_query": query, "answer": REFUSAL, "sources": [], "refused": True,
                "retrieval": [], "retrieval_s": 0.0, "generation_s": 0.0}
        if unsupported_request(question) or unsupported_request(query): return base
        start = time.perf_counter()
        with self._retrieval_lock:
            passages = self.engine.retrieve(query)
        base["retrieval_s"] = time.perf_counter() - start
        base["retrieval"] = [{"rank": p["rank"], "chunk_id": p["chunk_id"], "record_id": p["record_id"],
                              "source_ref": p["source_ref"], "similarity": p["similarity"]} for p in passages]
        if not passages or passages[0]["similarity"] < self.engine.config.min_similarity: return base
        start = time.perf_counter()
        answer = self.generator.answer(question, passages, history, query)
        base["generation_s"] = time.perf_counter() - start
        base["answer"] = answer
        base["refused"] = looks_like_refusal(answer)
        citations = [int(n) for n in re.findall(r"\[(\d+)\]", answer)]
        if any(n < 1 or n > len(passages) for n in citations):
            raise ValueError("The generated answer cited an unavailable passage.")
        if not base["refused"]:
            if not citations: raise ValueError("The generated factual answer has no source citation.")
            base["sources"] = [{"n": i, "ref": p["source_ref"], "question": p["question"],
                "option": p["option"], "text": safe_excerpt(p["text"]), "similarity": p["similarity"],
                "record_id": p["record_id"], "chunk_id": p["chunk_id"]} for i, p in enumerate(passages, 1)]
        return base
