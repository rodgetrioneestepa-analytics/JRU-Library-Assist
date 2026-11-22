import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as Obj
import unittest
from rag_backend.core import ROOT, SPEC, Config, load_workbook_records, clean_history
from rag_backend.generation import ConversationalGroq


def completion(value):
    return Obj(choices=[Obj(message=Obj(content=value))])


def generator_with(create):
    return ConversationalGroq(client=Obj(chat=Obj(completions=Obj(create=create))))


class ConversationTests(unittest.TestCase):
    def test_corrected_notebook_settings_and_prompts(self):
        self.assertEqual(SPEC['ACTIVE_CONFIG'], 'B')
        self.assertEqual((Config().chunk_size, Config().chunk_overlap), (800, 100))
        self.assertEqual(SPEC['MAX_HISTORY_MESSAGES'], 6)
        self.assertIn('Use the recent chat ONLY to resolve pronouns and references', SPEC['REWRITE_PROMPT'])
        self.assertIn('NOT for factual evidence', SPEC['ANSWER_PROMPT'])

    def test_blank_rewrites_never_index_empty_choices_or_lines(self):
        h = [{'role': 'user', 'content': 'Can students borrow a laptop?'}]
        for response in [Obj(), Obj(choices=[]), Obj(choices=None), completion(None), completion('  \n\n')]:
            gen = generator_with(lambda **kwargs: response)
            self.assertEqual(gen.standalone_question('And faculty?', h), 'And faculty?')

    def test_rewrite_errors_and_short_outputs_preserve_original(self):
        def failed(**kwargs): raise RuntimeError('offline')
        for create in [failed, lambda **kwargs: completion('x')]:
            self.assertEqual(generator_with(create).standalone_question('What about faculty?', [{'role': 'user', 'content': 'laptop'}]), 'What about faculty?')

    def test_answer_prompt_uses_current_passages_and_history_separately(self):
        calls = []
        def create(**kwargs): calls.append(kwargs); return completion('The library opens at seven. [1]')
        gen = generator_with(create)
        result = gen.answer('When does it open?', [{'source_ref': 'Basic Information!4', 'text': 'CURRENT PASSAGE'}], [{'role': 'user', 'content': 'PRIOR TURN'}], 'When does the library open?')
        self.assertIn('[1]', result)
        prompt = calls[0]['messages'][1]['content']
        self.assertIn('CURRENT VERIFIED FAQ PASSAGES', prompt)
        self.assertIn('reference resolution only; not a source of facts', prompt)
        self.assertEqual(calls[0]['max_completion_tokens'], 700)

    def test_workbook_layouts_and_duplicate_provenance(self):
        from openpyxl import Workbook
        with TemporaryDirectory() as tmp:
            book = Workbook(); wide = book.active; wide.title = 'FAQs'
            wide.cell(7, 1, 'OPAC'); wide.cell(8, 1, 'What is OPAC?'); wide.cell(8, 2, 'Online Public Access Catalog')
            topic = book.create_sheet('OPAC')
            topic.append(['KEYWORD', 'FAQs', 'OPTIONS', 'ANSWERS'])
            topic.append(['OPAC', 'What is OPAC?', '', 'Online Public Access Catalog'])
            path = Path(tmp) / 'test.xlsx'; book.save(path)
            result = load_workbook_records(path)
            self.assertEqual(result['raw_records'], 2)
            self.assertEqual(len(result['records']), 1)
            self.assertEqual(result['records'][0]['source_refs'], ['FAQs!8', 'OPAC!2'])

    def test_api_passes_only_bounded_per_request_history(self):
        from rag_backend.app import create_app
        source = json.loads((ROOT / 'server_data/faqs.json').read_text(encoding='utf-8'))
        item = source['records'][0]
        class Engine:
            def retrieve(self, query): return [{'record_id': item['record_id'], 'source_ref': item['source_ref'], 'text': item['answer'], 'similarity': .9}]
        class Generator:
            def standalone_question(self, message, history): self.history = history; return message
            def answer(self, *args): return 'A supported answer. [1]'
        gen = Generator(); client = create_app(engine=Engine(), generator=gen, source=source).test_client()
        self.assertEqual(client.get('/api/status').json, {'ready': True, 'service': 'Library-Assist'})
        history = [{'role': 'user', 'content': str(i)} for i in range(12)]
        response = client.post('/api/chat', json={'message': 'What are the library hours?', 'history': history})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(gen.history), 6)
        self.assertEqual(set(response.json), {'answer', 'refused'})
        client.post('/api/chat', json={'message': 'Another visitor question'})
        self.assertEqual(gen.history, [])
        self.assertEqual(client.post('/api/chat', json={'message': ''}).status_code, 400)


if __name__ == '__main__': unittest.main()
