"""Conversational Groq generation, including the corrected empty-rewrite guard."""
from .core import SPEC, REFUSAL, clean_history, safe_excerpt


def completion_content(completion):
    choices = getattr(completion, "choices", None) or []
    message = getattr(choices[0], "message", None) if choices else None
    return getattr(message, "content", None) or ""


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
        response = self.client.chat.completions.create(model=self.model, temperature=0, max_completion_tokens=700,
            messages=[{"role": "system", "content": SPEC["ANSWER_PROMPT"]}, {"role": "user", "content": prompt}])
        return safe_excerpt(completion_content(response).strip() or REFUSAL)
