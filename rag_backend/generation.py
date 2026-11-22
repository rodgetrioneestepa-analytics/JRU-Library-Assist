"""Conversational Groq generation, including the corrected empty-rewrite guard."""
import logging
import re
import json
from .core import SPEC, REFUSAL, clean, clean_history, safe_excerpt, looks_like_refusal


def completion_content(completion):
    choices = getattr(completion, "choices", None) or []
    message = getattr(choices[0], "message", None) if choices else None
    return getattr(message, "content", None) or ""


def render_cited_repair(content, passages):
    """Render only explicit model-selected references; never infer a source number."""
    result = json.loads(content)
    if not isinstance(result, dict) or type(result.get("refused")) is not bool:
        raise ValueError("Invalid structured citation response.")
    if result["refused"]: return REFUSAL
    claims = result.get("claims")
    if not isinstance(claims, list) or not claims: raise ValueError("No supported claims in citation response.")
    answer = {}
    for claim in claims:
        if not isinstance(claim, dict): raise ValueError("Invalid claim.")
        n, text, quote = claim.get("passage_number"), claim.get("text"), claim.get("source_quote")
        if type(n) is not int or not 1 <= n <= len(passages) or not isinstance(text, str) or not text.strip():
            raise ValueError("Invalid claim citation.")
        if not isinstance(quote, str) or not clean(quote) or clean(safe_excerpt(quote)).casefold() not in clean(safe_excerpt(passages[n-1]['text'])).casefold():
            raise ValueError("The supporting quote does not occur in the selected passage.")
        text = safe_excerpt(text.strip())
        key = clean(text).casefold()
        entry = answer.setdefault(key, {"text":text,"numbers":[]})
        if n not in entry['numbers']: entry['numbers'].append(n)
    return "\n".join(p['text']+' '+''.join(f'[{n}]' for n in p['numbers']) for p in answer.values())


class ConversationalGroq:
    def __init__(self, key=None, model="openai/gpt-oss-20b", client=None):
        if client is None:
            from groq import Groq
            client = Groq(api_key=key, timeout=45, max_retries=1)
        self.client, self.model = client, model

    def standalone_question(self, latest, history):
        latest = str(latest).strip()
        history = clean_history(history)
        if not history: return latest
        compact = "\n".join(f"{t['role']}: {t['content'][:350]}" for t in history)[:1600]
        try:
            response = self.client.chat.completions.create(model=self.model, temperature=0, max_completion_tokens=450,
                messages=[{"role": "system", "content": SPEC["REWRITE_PROMPT"]},
                          {"role": "user", "content": f"Recent chat:\n{compact}\n\nLatest message: {latest}"}])
            lines = [line.strip() for line in completion_content(response).splitlines() if line.strip()]
            if not lines: return latest
            rewritten = lines[0].strip(" \"'`•")
            return rewritten if 5 <= len(rewritten) <= 350 else latest
        except Exception:
            return latest

    def answer(self, question, passages, history, retrieval_query):
        evidence = "\n\n".join(f"[{i}] ({p['source_ref']}) {safe_excerpt(p['text'])}" for i, p in enumerate(passages, 1))[:7000]
        recent = "\n".join(f"{t['role']}: {t['content'][:450]}" for t in clean_history(history))[:1800]
        prompt = (f"RECENT CHAT (reference resolution only; not a source of facts):\n{recent or '(none)'}\n\n"
                  f"CURRENT VERIFIED FAQ PASSAGES:\n{evidence}\n\nStudent's latest message: {question}\nRetrieval interpretation: {retrieval_query}")
        messages = [{"role": "system", "content": SPEC["ANSWER_PROMPT"]}, {"role": "user", "content": prompt}]
        def complete(turns, **options):
            response = self.client.chat.completions.create(model=self.model, temperature=0,
                max_completion_tokens=700, messages=turns, **options)
            choices = getattr(response, "choices", None) or []
            if choices and getattr(choices[0], "finish_reason", None) == "length":
                logging.getLogger(__name__).warning("Groq completion reached the notebook token limit")
            return safe_excerpt(completion_content(response).strip() or REFUSAL)

        answer = complete(messages)
        if looks_like_refusal(answer): return REFUSAL
        # Extra website safeguard: one evidence check after the notebook draft.
        # Keep the notebook's first request, evidence, model and token settings intact.
        if answer:
            schema = {"type":"object", "properties":{
                "refused":{"type":"boolean"},
                "claims":{"type":"array", "items":{"type":"object", "properties":{
                    "text":{"type":"string"},
                    "source_quote":{"type":"string"},
                    "passage_number":{"type":"integer", "enum":list(range(1,len(passages)+1))}},
                    "required":["text","passage_number","source_quote"], "additionalProperties":False}}},
                "required":["refused","claims"], "additionalProperties":False}
            content = complete(messages + [
                {"role": "assistant", "content": answer},
                {"role": "user", "content": (
                    "Verify and correct that draft using only the CURRENT VERIFIED FAQ PASSAGES above. "
                    "Return JSON with refused and claims. For an answer, set refused=false and provide "
                    "at most three concise claims. Each claim must contain text, passage_number, and source_quote. "
                    "Copy a short exact supporting quote from that CURRENT passage. It must establish the entire "
                    "claim, not just a related topic. Do not infer guarantees or new permissions from a restriction. "
                    "The text must not contain citation "
                    "markers; the selected passage_number will be rendered as its citation. Use only passage "
                    "numbers that exist above. Remove unsupported claims; do not treat the draft as evidence. "
                    "If ANY part of the student's question is not established by the current passages, "
                    "set refused=true and claims=[] instead of answering only part or guessing. "
                    "Do not describe the check or the draft.")}
            ], response_format={"type":"json_schema", "json_schema":{
                "name":"cited_library_answer", "strict":True, "schema":schema}})
            answer = render_cited_repair(content, passages)
        return answer
