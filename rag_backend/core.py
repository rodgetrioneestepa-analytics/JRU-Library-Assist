"""FAQ-aware workbook retrieval adapted from the corrected conversational notebook."""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((Path(__file__).parent / "notebook_spec.json").read_text(encoding="utf-8"))
REFUSAL = SPEC["REFUSAL"]


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value):
    return clean(value).casefold()


def safe_excerpt(text):
    return re.sub(r"(?i)(account\s*(?:number|no\.?)[^\n:]*[:\s]+)\d[\d -]{5,}",
                  r"\1[REDACTED — CONFIRM WITH LIBRARY]", str(text))


def record(sheet, row, category, question, option, answer):
    return {"source_sheet": sheet, "source_row": row, "source_ref": f"{sheet}!{row}",
            "category": clean(category), "question": clean(question),
            "option": clean(option), "answer": clean(answer)}


def topic_records(sheet):
    question, category = "", sheet.title
    for row_no, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
        values = [clean(value) for value in row[:4]]
        values += [""] * (4 - len(values))
        key, current_q, option, answer = values
        if key and norm(key) != "keyword": category = key
        if current_q and norm(current_q) != "faqs": question = current_q
        if answer and question and norm(answer) != "answers":
            yield record(sheet.title, row_no, category, question, option, answer)


def consolidated_records(sheet):
    rows = sheet.iter_rows(values_only=True)
    for _ in range(6): next(rows, None)
    headers = next(rows, ())
    categories = {col: clean(headers[col]) for col in range(0, len(headers) - 1, 3)}
    for row_no, values in enumerate(rows, 8):
        for col, category in categories.items():
            question = clean(values[col]) if col < len(values) else ""
            answer = clean(values[col + 1]) if col + 1 < len(values) else ""
            if question and answer and question != chr(92) and category:
                yield record(sheet.title, row_no, category, question, "", answer)


def load_workbook_records(path):
    from openpyxl import load_workbook
    path = Path(path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = list(workbook.sheetnames)
        raw = [item for sheet in workbook
               for item in (consolidated_records if sheet.title in {"FAQs", "From Bert"} else topic_records)(sheet)]
    finally:
        workbook.close()
    unique = {}
    for item in raw:
        key = "|".join(norm(item[field]) for field in ["question", "option", "answer"])
        uid = hashlib.sha1(key.encode()).hexdigest()[:16]
        if uid in unique: unique[uid]["source_refs"].append(item["source_ref"])
        else: unique[uid] = {**item, "record_id": uid, "id": uid, "source_refs": [item["source_ref"]]}
    answers = defaultdict(set)
    for item in unique.values(): answers[(norm(item["question"]), norm(item["option"]))].add(norm(item["answer"]))
    for item in unique.values():
        item["review_flag"] = len(answers[(norm(item["question"]), norm(item["option"]))]) > 1 or bool(re.search(r"pandemic|until further notice|account\s*(number|no)", item["answer"], re.I))
        item["answer"] = safe_excerpt(item["answer"])
    return {"dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "worksheets": sheets, "raw_records": len(raw), "records": list(unique.values())}


@dataclass(frozen=True)
class Config:
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 3
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"
    min_similarity: float = .35

    def __post_init__(self):
        if self.chunk_size <= 0 or not 0 <= self.chunk_overlap < self.chunk_size or self.top_k <= 0:
            raise ValueError("Invalid chunk size, overlap, or result count.")


def chunk_records(records, config):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""])
    chunks = []
    for item in records:
        text = f"Topic: {item['category']}\nQuestion: {item['question']}\nOption: {item['option']}\nAnswer: {item['answer']}"
        for part, passage in enumerate(splitter.split_text(text)):
            chunks.append({"chunk_id": f"{item['record_id']}_{part}", "record_id": item["record_id"],
                "text": passage, "source_ref": item["source_ref"], "source_sheet": item["source_sheet"],
                "question": item["question"], "option": item["option"], "review_flag": item["review_flag"]})
    return chunks


class SemanticIndex:
    def __init__(self, records, config, encoder=None, client=None):
        from sentence_transformers import SentenceTransformer
        import chromadb
        self.config, self.records = config, records
        self.chunks = chunk_records(records, config)
        self.encoder = encoder or SentenceTransformer(config.embedding_model, device=config.device,
            cache_folder=str(ROOT / ".model-cache"), trust_remote_code=False)
        client = client or chromadb.PersistentClient(path=str(ROOT / ".chroma-cache"))
        fingerprint = hashlib.sha256(json.dumps([config.embedding_model, self.chunks], sort_keys=True).encode()).hexdigest()[:20]
        self.collection = client.get_or_create_collection("jru_faq_" + fingerprint, metadata={"hnsw:space": "cosine"})
        if self.collection.count() == 0:
            vectors = self.encoder.encode([c["text"] for c in self.chunks], batch_size=32,
                normalize_embeddings=True, show_progress_bar=False).tolist()
            for offset in range(0, len(self.chunks), 100):
                batch = self.chunks[offset:offset + 100]
                self.collection.add(ids=[c["chunk_id"] for c in batch], documents=[c["text"] for c in batch],
                    metadatas=[{k: str(v) for k, v in c.items() if k != "text"} for c in batch],
                    embeddings=vectors[offset:offset + 100])
        if self.collection.count() != len(self.chunks):
            raise ValueError("The cached collection is incomplete; use a fresh cache before restarting.")

    def retrieve(self, question, top_k=None):
        if not isinstance(question, str) or not question.strip(): raise ValueError("Enter a question.")
        vector = self.encoder.encode(question, normalize_embeddings=True).tolist()
        result = self.collection.query(query_embeddings=[vector], n_results=min(top_k or self.config.top_k, self.collection.count()),
            include=["documents", "metadatas", "distances"])
        return [{**metadata, "text": text, "rank": rank, "similarity": 1 - float(distance)}
                for rank, (text, metadata, distance) in enumerate(zip(result["documents"][0], result["metadatas"][0], result["distances"][0]), 1)]


def clean_history(history):
    if not isinstance(history, list): return []
    return [{"role": turn["role"], "content": safe_excerpt(turn["content"][:1000])}
            for turn in history if isinstance(turn, dict) and turn.get("role") in {"user", "assistant"}
            and isinstance(turn.get("content"), str)][-6:]


def unsupported_request(question):
    q = norm(question)
    return bool(re.search(r"(?:what is|tell me|give me).*?(?:wi.?fi password|network password)", q)
                or re.search(r"right now|at this exact moment|currently available seats|on duty now", q))


def looks_like_refusal(answer):
    text = norm(answer).replace("’", "'")
    return any(p in text for p in ["couldn't confirm", "could not confirm", "can't confirm", "cannot confirm",
        "unable to confirm", "couldn't verify", "cannot verify", "not stated in the", "not provided in the", "don't have that information", "do not have that information"])


def basic_social_reply(message):
    m = norm(message).strip("!?. ")
    if m in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}:
        return "Hi! I can help with library hours, borrowing, renewals, and more. What would you like to know?"
    if m in {"thanks", "thank you", "thank you so much", "salamat", "salamat po"}:
        return "You're welcome! Feel free to ask another library question."
    if m in {"bye", "goodbye", "see you"}: return "Take care! Come back anytime you need library help."
    if m in {"help", "what can you do", "how can you help"}:
        return "I can help with borrowing, renewals, fines, OPAC, electronic resources, and library facilities."
    return None
