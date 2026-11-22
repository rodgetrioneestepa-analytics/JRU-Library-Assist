import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch
from rag_backend.core import ROOT, SPEC, REFUSAL, Config, load_workbook_records, clean_history, prepare_source, resolve_source, safe_excerpt
from rag_backend.generation import ConversationalGroq, render_cited_repair
from rag_backend.service import ChatService


def completion(value):
    return Obj(choices=[Obj(message=Obj(content=value))])


def verified(text, quote, n=1):
    return json.dumps({'refused':False,'claims':[{'text':text,'passage_number':n,'source_quote':quote}]})


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
        def create(**kwargs):
            calls.append(kwargs)
            return completion(verified('The library opens at seven.','CURRENT PASSAGE') if 'response_format' in kwargs else 'The library opens at seven. [1]')
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
            config = Config()
            def retrieve(self, query): return [{**item, 'rank': 1, 'chunk_id': item['record_id']+'_0', 'text': item['answer'], 'similarity': .9}]
        class Generator:
            def standalone_question(self, message, history): self.history = history; return message
            def answer(self, *args): return 'A supported answer. [1]'
        gen = Generator(); client = create_app(engine=Engine(), generator=gen, source=source).test_client()
        self.assertTrue(client.get('/api/status').json['ready'])
        self.assertEqual(client.get('/api/status').json['pipeline'], 'minilm-chroma-groq')
        history = [{'role': 'user', 'content': str(i)} for i in range(12)]
        response = client.post('/api/chat', json={'message': 'What are the library hours?', 'history': history})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(gen.history), 6)
        self.assertEqual(response.json['answer'], 'A supported answer. [1]')
        self.assertEqual(response.json['sources'][0]['ref'], item['source_ref'])
        self.assertEqual(response.json['retrieval'][0]['rank'], 1)
        client.post('/api/chat', json={'message': 'Another visitor question'})
        self.assertEqual(gen.history, [])
        self.assertEqual(client.post('/api/chat', json={'message': ''}).status_code, 400)

    def test_missing_groq_does_not_fall_back_to_stored_faq_answers(self):
        from rag_backend.app import Runtime
        with patch.dict('os.environ', {'GROQ_API_KEY': ''}):
            with self.assertRaisesRegex(RuntimeError, 'GROQ_API_KEY'): Runtime().initialize()

    def test_unsupported_and_low_similarity_never_call_generation(self):
        class Engine:
            config = Config()
            calls = 0
            def retrieve(self, query):
                self.calls += 1
                return [{'rank': 1, 'chunk_id': 'a_0', 'record_id': 'a', 'source_ref': 'OPAC!3', 'similarity': .3499}]
        class Generator:
            def standalone_question(self, q, h): return q
            def answer(self, *args): raise AssertionError('Generation must not run')
        engine = Engine(); service = ChatService(engine, Generator())
        for question in ['What is the actual Wi-Fi password for JRU LIB3?', 'How many seats are empty right now?', 'Which librarian is on duty now?']:
            result = service.chat(question)
            self.assertEqual(result['answer'], REFUSAL)
            self.assertEqual(result['retrieval'], [])
        self.assertEqual(engine.calls, 0)
        self.assertEqual(service.chat('What is OPAC?')['answer'], REFUSAL)
        self.assertEqual(engine.calls, 1)

    def test_citations_must_refer_to_current_passages(self):
        item = {'rank': 1, 'chunk_id': 'a_0', 'record_id': 'a', 'source_ref': 'OPAC!3', 'similarity': .9, 'question': 'OPAC?', 'option': '', 'text': 'Online Public Access Catalog'}
        engine = Obj(config=Config(), retrieve=lambda q: [item])
        for answer in ['The catalog. [4]', 'The catalog.']:
            generator = Obj(standalone_question=lambda q,h:q, answer=lambda *args:answer)
            with self.assertRaises(ValueError): ChatService(engine, generator).chat('What is OPAC?')

    def test_payment_text_is_redacted_before_groq(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return completion(verified('Please confirm payment details with staff.',safe_excerpt('Account number: 123456789012')) if 'response_format' in kwargs else 'Please confirm payment details with staff. [1]')
        generator_with(create).answer('How do I pay?', [{'source_ref':'Fines!5','text':'Account number: 123456789012'}], [], 'How do I pay?')
        self.assertNotIn('123456789012', calls[0]['messages'][1]['content'])
        self.assertIn('[REDACTED', calls[0]['messages'][1]['content'])

    def test_missing_citations_get_one_repair_with_same_evidence_and_settings(self):
        calls = []
        responses = iter(['Saturday hours are seven to five.', verified('Saturday hours are seven to five.','Saturday: 7 AM to 5 PM')])
        def create(**kwargs): calls.append(kwargs); return completion(next(responses))
        answer = generator_with(create).answer('Saturday hours?', [{'source_ref':'Basic Information!4','text':'Saturday: 7 AM to 5 PM'}], [], 'Saturday hours?')
        self.assertEqual(answer, 'Saturday hours are seven to five. [1]')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['messages'][:2], calls[0]['messages'])
        self.assertEqual(calls[1]['messages'][2]['role'], 'assistant')
        self.assertIn('do not treat the draft as evidence', calls[1]['messages'][3]['content'])
        self.assertNotIn('response_format', calls[0])
        self.assertTrue(calls[1]['response_format']['json_schema']['strict'])
        self.assertEqual(calls[1]['response_format']['json_schema']['schema']['properties']['claims']['items']['properties']['passage_number']['enum'], [1])
        for call in calls:
            self.assertEqual(call['model'], SPEC['GROQ_MODEL'])
            self.assertEqual(call['temperature'], 0)
            self.assertEqual(call['max_completion_tokens'], 700)

    def test_citation_repair_is_bounded_and_still_fails_closed(self):
        calls = []
        def create(**kwargs): calls.append(kwargs); return completion('Uncited draft.')
        gen = generator_with(create)
        item = {'rank':1,'chunk_id':'a_0','record_id':'a','source_ref':'OPAC!3','similarity':.9,'question':'OPAC?','option':'','text':'Catalog'}
        with self.assertRaises(ValueError):
            ChatService(Obj(config=Config(),retrieve=lambda q:[item]),gen).chat('What is OPAC?')
        self.assertEqual(len(calls), 2)

    def test_structured_repairs_cannot_invent_passage_numbers(self):
        self.assertEqual(render_cited_repair(json.dumps({'refused':True,'claims':[]}),[{'text':'Catalog'}]*3),REFUSAL)
        for result in [
            {'refused':False,'claims':[]},
            {'refused':False,'claims':[{'text':'Unsupported','passage_number':4}]},
            {'refused':False,'claims':[{'text':'Unsupported','passage_number':True}]},
            {'refused':'false','claims':[{'text':'Unsupported','passage_number':1}]}]:
            with self.assertRaises(ValueError): render_cited_repair(json.dumps(result),[{'text':'Catalog'}]*3)

    def test_supporting_quotes_must_exist_and_duplicate_claims_are_merged(self):
        passages = [{'text':'Online Public Access Catalog'}]*2
        with self.assertRaisesRegex(ValueError, 'supporting quote'):
            render_cited_repair(verified('The catalog.','Nonexistent policy'),passages)
        payload = {'refused':False,'claims':[
            {'text':'The catalog.','passage_number':1,'source_quote':'Public Access Catalog'},
            {'text':'The catalog.','passage_number':2,'source_quote':'Public Access Catalog'}]}
        self.assertEqual(render_cited_repair(json.dumps(payload),passages),'The catalog. [1][2]')

    def test_rate_limits_are_reported_as_429_with_retry_after(self):
        from groq import RateLimitError
        import httpx
        from rag_backend.app import create_app
        item = {'rank':1,'chunk_id':'a_0','record_id':'a','source_ref':'OPAC!3','similarity':.9,'question':'OPAC?','option':'','text':'Catalog'}
        def limited(*args):
            raise RateLimitError('limit',response=httpx.Response(429,headers={'retry-after':'2.1'},request=httpx.Request('POST','https://api.groq.com/openai/v1/chat/completions')),body=None)
        gen = Obj(standalone_question=lambda q,h:q,answer=limited)
        client = create_app(engine=Obj(config=Config(),retrieve=lambda q:[item]),generator=gen).test_client()
        response = client.post('/api/chat',json={'message':'What is OPAC?'})
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['Retry-After'],'3')
        self.assertIn('request limit',response.json['error'])

    def test_schema_rejection_uses_json_mode_without_relaxing_quote_checks(self):
        import httpx
        from groq import BadRequestError
        calls=[]
        def create(**kwargs):
            calls.append(kwargs)
            mode=kwargs.get('response_format',{}).get('type')
            if mode=='json_schema':
                raise BadRequestError('schema unsupported',response=httpx.Response(400,request=httpx.Request('POST','https://api.groq.com/openai/v1/chat/completions')),body={'error':{'code':'invalid_request_error'}})
            return completion(verified('The catalog.','Public Access Catalog') if mode=='json_object' else 'The catalog. [1]')
        answer=generator_with(create).answer('OPAC?', [{'source_ref':'OPAC!3','text':'Online Public Access Catalog'}],[],'OPAC?')
        self.assertEqual(answer,'The catalog. [1]')
        self.assertEqual([c.get('response_format',{}).get('type') for c in calls],[None,'json_schema','json_object'])
        self.assertEqual(calls[1]['messages'],calls[2]['messages'])

    def test_prepared_source_rejects_missing_or_changed_private_override(self):
        from rag_backend import core
        source = {'worksheets':core.EXPECTED_SHEETS, 'records':[{'record_id':'a','answer':'Account number: 123456789012'}]}
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)/'server_data'
            prepare_source(source, directory)
            self.assertNotIn('123456789012', (directory/'faqs.json').read_text(encoding='utf8'))
            with patch.object(core, 'ROOT', Path(tmp)), patch.dict('os.environ', {'RAG_WORKBOOK':'', 'RAG_PRIVATE_RECORD_OVERRIDES':''}):
                self.assertEqual(resolve_source()['records'], source['records'])
                (directory/'private-overrides.json').unlink()
                with self.assertRaisesRegex(RuntimeError, 'Private source configuration'): resolve_source()


if __name__ == '__main__': unittest.main()
