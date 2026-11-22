"""Compare reviewed notebook functions with the app; never run notebook setup/export cells.

Local mode uses a deterministic completion stub to compare exact Groq request payloads,
not to claim real LLM quality. --url mode tests actual deployed Groq responses against
the local retrieval baseline. Reports contain source IDs/scores and redacted answers.
"""
import argparse
import ast
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from types import SimpleNamespace as Obj
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag_backend.core import SPEC, REFUSAL, Config, SemanticIndex, resolve_source, safe_excerpt
from rag_backend.generation import ConversationalGroq
from rag_backend.service import ChatService


def trace(passages):
    return [{k: p[k] for k in ('rank', 'chunk_id', 'record_id', 'source_ref', 'similarity')} for p in passages]


def same_ranking(left, right, tolerance=1e-6):
    return len(left) == len(right) and all(
        all(a[k] == b[k] for k in ('rank', 'chunk_id', 'record_id', 'source_ref'))
        and abs(a['similarity'] - b['similarity']) <= tolerance for a, b in zip(left, right))


def oracle(notebook_path, workbook_path, encoder, client):
    from openpyxl import load_workbook
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    cells = json.loads(Path(notebook_path).read_text(encoding='utf8'))['cells']
    ns = dict(re=re, time=time, hashlib=hashlib, defaultdict=defaultdict,
              RecursiveCharacterTextSplitter=RecursiveCharacterTextSplitter,
              ACTIVE_CONFIG='B', CONFIGS=[{'id':'B','size':800,'overlap':100,'top_k':3}],
              MIN_SIMILARITY=.35, GROQ_MODEL=SPEC['GROQ_MODEL'], MAX_HISTORY_MESSAGES=6,
              REWRITE_FOLLOWUPS=True, REFUSAL=REFUSAL, encoder=encoder, client=client,
              collections={}, chunk_tables={})
    expected = {16:{'clean','norm','record'},19:{'topic_records'},22:{'consolidated_records'},
                45:{'chunk_records'},48:{'new_collection'},51:{'build_index'},54:{'retrieve'},
                61:{'unsupported_request','safe_excerpt','looks_like_refusal'},
                64:{'answer_question'},67:{'standalone_search_question'},70:{'basic_social_reply'}}
    for index, names in expected.items():
        tree = ast.parse(''.join(cells[index]['source']))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        assert {n.name for n in nodes} == names, f'Notebook functions changed in cell {index}'
        exec(compile(ast.Module(body=nodes, type_ignores=[]), f'notebook-cell-{index}', 'exec'), ns)
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    ns['raw_records'] = [r for sheet in workbook for r in ns['consolidated_records' if sheet.title in {'FAQs','From Bert'} else 'topic_records'](sheet)]
    ns['worksheets'] = list(workbook.sheetnames)
    workbook.close()
    # Only the reviewed data transformations; no notebook filesystem/network exports.
    for index in (28,31):
        tree = ast.parse(''.join(cells[index]['source']))
        nodes = []
        for node in tree.body:
            if isinstance(node, ast.Expr): break
            nodes.append(node)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), f'notebook-cell-{index}', 'exec'), ns)
    return ns


class Capture:
    def __init__(self): self.calls = []; self.passages = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if 'response_format' in kwargs:
            content = json.dumps({'refused':False,'claims':[{'text':'A supported response.', 'passage_number':1, 'source_quote':safe_excerpt(self.passages[0]['text'][:120])}]})
            return Obj(choices=[Obj(message=Obj(content=content))])
        # Shared visible completion tests prompt equivalence; not an LLM evaluation.
        return Obj(choices=[Obj(message=Obj(content='A supported response. [1]'))])


def local(args):
    import chromadb
    from sentence_transformers import SentenceTransformer
    source = resolve_source()
    encoder = SentenceTransformer(Config().embedding_model, device='cpu', cache_folder=str(ROOT/'.model-cache'), trust_remote_code=False)
    # Chroma's Windows native handles can outlive Python objects at interpreter exit.
    with tempfile.TemporaryDirectory(prefix='jru-parity-', ignore_cleanup_errors=True) as tmp:
        ns = oracle(args.notebook, args.workbook, encoder, chromadb.PersistentClient(path=str(Path(tmp)/'reference')))
        app_records = [{k:v for k,v in r.items() if k != 'id'} for r in source['records']]
        assert app_records == ns['records'], 'Workbook processing differs from notebook'
        assert source['worksheets'] == ns['worksheets']
        assert source['raw_records'] == len(ns['raw_records'])
        ns['build_index'](ns['CONFIGS'][0])
        engine = SemanticIndex(source['records'], Config(), encoder=encoder,
            client=chromadb.PersistentClient(path=str(Path(tmp)/'app')), source_sha256=source['dataset_sha256'])
        assert engine.chunks == ns['chunk_tables']['B'], 'Chunk text/metadata differs'
        captured_reference, captured_app = Capture(), Capture()
        ns['groq_client'] = Obj(chat=Obj(completions=captured_reference))
        gen = ConversationalGroq(client=Obj(chat=Obj(completions=captured_app)))
        service = ChatService(engine, gen)
        cases = []
        for qid, difficulty, question, gold in SPEC['TEST_PLAN']:
            case = {'id':qid, 'difficulty':difficulty, 'question':question, 'gold_sources':gold}
            # TEST_PLAN is the notebook's literal list; do not replace it with easier queries.
            q = case['question']
            captured_reference.calls.clear(); captured_app.calls.clear()
            reference = ns['answer_question'](q)
            captured_app.passages = reference['passages']
            actual = service.chat(q)
            left, right = trace(reference['passages']), actual['retrieval']
            ranking = same_ranking(left, right)
            prompts = (captured_reference.calls == captured_app.calls[:len(captured_reference.calls)] and
                       (len(captured_app.calls)==2 if captured_reference.calls else not captured_app.calls))
            refused = reference['refused'] == actual['refused'] and reference['answer'] == actual['answer']
            gold_refs = case.get('gold_sources', case.get('gold_refs', []))
            required = {ns['source_to_id'][ref] for ref in gold_refs}
            retrieved = {p['record_id'] for p in left}
            coverage = len(required & retrieved)/len(required) if required else None
            result = {**case, 'ranking_match':ranking, 'groq_payload_match':prompts,
                      'turn_path_match':refused, 'gold_coverage':coverage, 'retrieval':left,
                      'extra_verification_calls':max(0,len(captured_app.calls)-len(captured_reference.calls)),
                      'expected_refusal':reference['refused'], 'passed':ranking and prompts and refused}
            cases.append(result)
            print(f"{case.get('id',case.get('qid'))}: {'PASS' if result['passed'] else 'FAIL'}; gold coverage={coverage}", flush=True)
        # Context-dependent, new-topic, and new-session prompt paths, without external requests.
        history = [{'role':'user','content':'May students borrow a library laptop?'},
                   {'role':'assistant','content':'Ask staff about laptops. [1]'}]
        conversation = []
        for q,h in [('What about faculty?',history), ('What does OPAC stand for?',history), ('What does OPAC stand for?',[])]:
            captured_reference.calls.clear(); captured_app.calls.clear()
            expected = ns['standalone_search_question'](q,h)
            actual = gen.standalone_question(q,h)
            passed = expected == actual and captured_reference.calls == captured_app.calls
            conversation.append({'question':q,'history_messages':len(h),'prompt_match':passed})
        report = {'mode':'local-independent-notebook-functions', 'generation':'deterministic stub; Groq payload equivalence only',
                  'dataset_sha256':source['dataset_sha256'], 'raw_records':source['raw_records'], 'unique_records':len(source['records']),
                  'worksheets':source['worksheets'], 'chunks':len(engine.chunks), 'index_fingerprint':engine.fingerprint,
                  'model_weights_sha256':engine.model_fingerprint, 'encoder_shared_between_comparators':True,
                  'records_match':True,'chunks_match':True,'cases':cases,'conversation':conversation}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        assert all(c['passed'] for c in cases) and all(c['prompt_match'] for c in conversation)


def remote(args):
    baseline = json.loads(args.baseline.read_text(encoding='utf8'))
    cases = []
    def post(message, history=None):
        data = json.dumps({'message':message,'history':history or []}).encode()
        req = urllib.request.Request(args.url.rstrip('/')+'/api/chat', data=data, headers={'Content-Type':'application/json'})
        if args.pause: time.sleep(args.pause)
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req,timeout=240) as response: return response.status,json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt == 0:
                    delay = min(180,max(1,int(float(exc.headers.get('Retry-After','60')))))
                    print(f'Provider rate limit; respecting Retry-After ({delay}s)',flush=True)
                    while delay:
                        step = min(30,delay); time.sleep(step); delay -= step
                    continue
                return exc.code, {'error':'HTTP request failed'}
    for case in ([] if args.conversation_only else baseline['cases']):
        status, result = post(case['question'])
        ranking = same_ranking(case['retrieval'], result.get('retrieval',[]), tolerance=1e-4)
        citations = [int(n) for n in re.findall(r'\[(\d+)\]',result.get('answer',''))]
        sources = result.get('sources',[])
        source_valid = all(s['n'] <= len(result.get('retrieval',[])) and
            s['chunk_id'] == result['retrieval'][s['n']-1]['chunk_id'] and
            s['ref'] == result['retrieval'][s['n']-1]['source_ref'] for s in sources)
        refused = result.get('refused')
        citation_valid = (not sources if refused else bool(citations) and all(n in {s['n'] for s in sources} for n in citations))
        refusal_valid = ((refused and result.get('answer') == REFUSAL) if case['expected_refusal']
                         else (not refused if case['gold_coverage'] == 1 else True))
        safe = not re.search(r'account\s*(?:number|no\.?)[^\n:]*[:\s]+\d[\d -]{5,}',result.get('answer',''),re.I)
        passed = status==200 and ranking and source_valid and citation_valid and refusal_valid and safe
        item = {**case,'http_status':status,'ranking_match':ranking,'citation_valid':bool(source_valid and citation_valid),
                'refusal_valid':bool(refusal_valid),'answer':safe_excerpt(result.get('answer','')),'refused':refused,
                'retrieval':result.get('retrieval',[]),'passed':bool(passed)}
        cases.append(item)
        print(f"{case.get('id',case.get('qid'))}: {'PASS' if passed else 'FAIL'} HTTP {status}, ranking={ranking}, citations={citation_valid}, refused={refused}",flush=True)
    history = []; conversation=[]
    for q in ['May students borrow a library laptop?', 'What about faculty?', 'What does OPAC stand for?']:
        status,result = post(q,history)
        conversation.append({'question':q,'http_status':status,'retrieval_query':result.get('retrieval_query'),
            'answer':safe_excerpt(result.get('answer','')),'retrieval':result.get('retrieval',[]),'refused':result.get('refused')})
        if status==200: history.extend([{'role':'user','content':q},{'role':'assistant','content':result['answer']}])
        else: break
    status,reset = post('What does OPAC stand for?',[])
    conversation.append({'question':'What does OPAC stand for?','new_session':True,'http_status':status,
                         'retrieval_query':reset.get('retrieval_query'),'answer':safe_excerpt(reset.get('answer','')),
                         'retrieval':reset.get('retrieval',[])})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'mode':'deployed-live-groq','url':args.url,'cases':cases,'conversation':conversation},ensure_ascii=False,indent=2),encoding='utf8')
    assert all(c['passed'] for c in cases), 'Inspect report for deployment differences'
    assert len(conversation)==4 and all(c['http_status']==200 for c in conversation), 'Conversation request failed'
    assert 'faculty' in conversation[1]['retrieval_query'].casefold(), 'Faculty follow-up was not resolved'
    assert 'laptop' in conversation[1]['retrieval_query'].casefold(), 'Laptop context was lost'
    assert conversation[2]['retrieval_query'] == 'What does OPAC stand for?', 'Topic switch carried old context'
    assert conversation[3]['retrieval_query'] == 'What does OPAC stand for?', 'New session carried old context'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--notebook',type=Path)
    parser.add_argument('--workbook',type=Path)
    parser.add_argument('--url')
    parser.add_argument('--conversation-only',action='store_true')
    parser.add_argument('--pause',type=float,default=0,help='Seconds between live requests to respect provider quotas')
    parser.add_argument('--baseline',type=Path,default=ROOT/'.rag-results/notebook-parity-reference.json')
    parser.add_argument('--output',type=Path,default=ROOT/'.rag-results/notebook-parity-reference.json')
    args = parser.parse_args()
    if args.url: remote(args)
    else:
        if not args.notebook or not args.workbook: parser.error('Local mode requires --notebook and --workbook')
        local(args)
