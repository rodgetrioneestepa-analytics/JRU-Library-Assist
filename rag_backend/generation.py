import json
import re
from .core import ROOT, SPEC, REFUSAL, validate_payload


class GroqGenerator:
    def __init__(self, key, model="openai/gpt-oss-20b", client=None):
        from groq import Groq
        self.client = client or Groq(api_key=key, timeout=45, max_retries=1)
        self.model = model

    def answer(self, question, sources):
        response = self.client.chat.completions.create(
            model=self.model, temperature=0, max_completion_tokens=2048,
            reasoning_effort="low", include_reasoning=False,
            messages=[{"role": "system", "content": SPEC["FAQ_SYSTEM_PROMPT"]},
                      {"role": "user", "content": json.dumps({"question": question, "sources": sources}, ensure_ascii=False)}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "jru_faq_answer", "strict": True, "schema": SPEC["FAQ_RESPONSE_SCHEMA"]}},
        )
        choice = response.choices[0]
        if choice.finish_reason != "stop":
            raise ValueError("The completion did not finish normally.")
        return validate_payload(json.loads(choice.message.content or ""), sources)


class FlanGenerator:
    """Optional historical notebook baseline; retrieved context is not quote-validated."""
    def __init__(self, device="cpu"):
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        self.torch, self.device = torch, device
        self.tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-base", cache_dir=str(ROOT / ".model-cache"))
        self.model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-base", cache_dir=str(ROOT / ".model-cache")).to(device)
        self.model.eval()

    def answer(self, question, sources):
        prefix = (f"Question: {question}\n\nAnswer only using supplied evidence. Match the exact person, service, "
                  "conditions and restrictions requested. Do not guess or use outside knowledge. If unsupported, "
                  "say 'I cannot find the answer in the provided document.'\n\nEvidence:\n")
        suffix = "\n\nAnswer:"
        encode = lambda value: self.tokenizer.encode(value, add_special_tokens=False)
        remaining = 512 - len(encode(prefix)) - len(encode(suffix)) - 16 - 1
        if remaining <= 0:
            raise ValueError("Question leaves no room for evidence.")
        parts = []
        for source in sources:
            tokens = encode(f"[Page {source['page']}, Chunk {source['chunk_id']}]\n{source['text']}")
            separator = len(encode("\n\n")) if parts else 0
            available = remaining - separator
            if available <= 0:
                break
            parts.append(self.tokenizer.decode(tokens[:available], skip_special_tokens=True, clean_up_tokenization_spaces=False))
            remaining -= min(len(tokens), available) + separator
            if len(tokens) > available:
                break
        inputs = self.tokenizer(prefix + "\n\n".join(parts) + suffix, return_tensors="pt", truncation=False)
        if inputs["input_ids"].shape[1] > 512:
            raise ValueError("Prompt exceeds the notebook's 512-token limit.")
        with self.torch.no_grad():
            output = self.model.generate(**{key: value.to(self.device) for key, value in inputs.items()},
                max_new_tokens=32, do_sample=False, num_beams=4, early_stopping=True)
        answer = self.tokenizer.decode(output[0], skip_special_tokens=True).strip()
        if not answer:
            raise ValueError("The baseline model returned an empty answer.")
        return {"answer": answer, "status": "baseline", "citations": []}
