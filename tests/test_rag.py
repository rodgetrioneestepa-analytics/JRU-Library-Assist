import json
import unittest
from rag_backend.core import ROOT, SPEC, Config, create_chunks, extract_pdf, validate_payload


class NotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "public/data/notebook-source.json").read_text(encoding="utf-8"))
        cls.sources = [{"source_id": "S1", "page": 1, "chunk_id": 1, "text": "Only one student per chair is allowed."}]

    def test_pdf_fingerprint_and_all_nine_evidence_keys(self):
        extracted = extract_pdf(ROOT / "public/data/library-faq.pdf")
        self.assertEqual(extracted["dataset_sha256"], "e9daef1fe5201b08b8cda91a54ec4009d3046ab3d877973e4da0f56398ca54a6")
        self.assertEqual(extracted["pages"], self.source["pages"])
        pages = {p["page"]: p["text"] for p in extracted["pages"]}
        self.assertEqual(len(SPEC["TEST_QUESTIONS"]), 9)
        for question in SPEC["TEST_QUESTIONS"]:
            for evidence in question["evidence"]:
                self.assertIn(evidence["passage"], pages[evidence["page"]])

    def test_chunking_matches_notebook_counts_for_twelve_configs(self):
        expected = [41, 45, 52, 26, 29, 32, 17, 19, 20, 14, 16, 17]
        for config, count in zip(SPEC["EVAL_CONFIGS"], expected):
            chunks = create_chunks(self.source["pages"], config["chunk_size"], config["chunk_overlap"])
            self.assertEqual(len(chunks), count, config["config_id"])
            self.assertEqual(len({c["chunk_id"] for c in chunks}), count)
            self.assertTrue(all(len(c["text"]) <= config["chunk_size"] for c in chunks))
        with self.assertRaises(ValueError): Config(chunk_overlap=1000)

    def test_evidence_rejects_fabricated_quotes_and_ids(self):
        for citation in [{"source_id": "S9", "quote": "Only one student"}, {"source_id": "S1", "quote": "Two students are allowed"}]:
            with self.assertRaises(ValueError):
                validate_payload({"status": "answered", "answer": "A policy", "citations": [citation]}, self.sources)

    def test_insufficient_and_conflict_have_explicit_outcomes(self):
        result = validate_payload({"status": "insufficient", "answer": "A guess", "citations": []}, self.sources)
        self.assertIn("could not confirm", result["answer"])
        with self.assertRaises(ValueError):
            validate_payload({"status": "conflict", "answer": "Conflict", "citations": [{"source_id": "S1", "quote": "Only one student"}]}, self.sources)

    def test_api_contract_with_injected_engine_no_model_download(self):
        from rag_backend.app import create_app
        source = self.source
        class Engine:
            chunks = create_chunks(source["pages"])
            def sources(self, question, document):
                return [{**self.chunks[0], "source_id": "S0", "score": .8, "source_document": document}]
        client = create_app(engine=Engine(), source=source).test_client()
        self.assertEqual(client.get("/api/status").json["mode"], "faiss-excerpts")
        self.assertEqual(client.post("/api/chat", json={"message": ""}).status_code, 400)
        self.assertEqual(client.post("/api/chat", json={"message": "x" * 1001}).status_code, 400)
        response = client.post("/api/chat", json={"message": "Library hours?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["sources"][0]["page"], 1)
        self.assertIn("not a generated answer", response.json["answer"])


if __name__ == "__main__": unittest.main()
