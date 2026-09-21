import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import urllib.error

from fastapi.testclient import TestClient
from pypdf import PdfReader
import sympy as s

from jevtex import app as web, judge
from jevtex.tex import extract
from jevtex.pdf import ROOT, compile_tex, locate_equations, tex_environment, annotate


def answer(choice="correct", probabilities=None):
    return {"model": "mock-test", "answers": {"transition": {
        "type": "choice", "choice": choice, "confidence": 1,
        "probabilities": probabilities or {k: float(k == choice) for k in judge.CRITERIA}}}}


class CoreTests(unittest.TestCase):
    def test_extraction_nested_rows_comments_and_sections(self):
        source = r"""\documentclass{article}
\begin{document}
\section{First}
% \begin{equation}bad\end{equation}
\begin{align*}
A &= \begin{matrix}a\\b\end{matrix}\label{one}\\
 &= B % hidden answer
\end{align*}
\[B=C\]
\section{Second}
\begin{equation*}C=D\end{equation*}
\end{document}"""
        parsed = extract(source)
        self.assertEqual(len(parsed["equations"]), 4)
        self.assertEqual(len(parsed["pairs"]), 2)
        self.assertIn(r"a\\b", parsed["equations"][0]["latex"])
        self.assertEqual(parsed["equations"][0]["labels"], ["one"])
        self.assertEqual(parsed["equations"][1]["latex"], "A = B")
        self.assertNotIn("hidden", str(parsed["equations"]))
        with self.assertRaises(ValueError):
            extract(r"\begin{document}\input{secret}\end{document}")

    def test_physics_and_fixture_difference(self):
        r, t = s.symbols("r theta", positive=True)
        f = s.Function("f")(r,t)
        dx = lambda g: s.cos(t)*s.diff(g,r)-s.sin(t)/r*s.diff(g,t)
        dy = lambda g: s.sin(t)*s.diff(g,r)+s.cos(t)/r*s.diff(g,t)
        fr, frr, ft, ftt, frt = s.diff(f,r), s.diff(f,r,2), s.diff(f,t), s.diff(f,t,2), s.diff(f,r,t)
        xx = s.cos(t)**2*frr-2*s.sin(t)*s.cos(t)/r*frt+s.sin(t)**2/r**2*ftt+s.sin(t)**2/r*fr+2*s.sin(t)*s.cos(t)/r**2*ft
        yy = s.sin(t)**2*frr+2*s.sin(t)*s.cos(t)/r*frt+s.cos(t)**2/r**2*ftt+s.cos(t)**2/r*fr-2*s.sin(t)*s.cos(t)/r**2*ft
        self.assertEqual(s.simplify(dx(dx(f))-xx), 0)
        self.assertEqual(s.simplify(dy(dy(f))-yy), 0)
        self.assertEqual(s.simplify(xx+yy-(frr+fr/r+ftt/r**2)), 0)
        self.assertEqual(s.simplify(dx(dx(r**2))+dy(dy(r**2))), 4)
        self.assertEqual(s.diff(r**2,r,2)+s.diff(r**2,t,2)/r**2, 2)
        a = (ROOT/"examples/laplacian_correct.tex").read_text()
        b = (ROOT/"examples/laplacian_mistake.tex").read_text()
        self.assertEqual(b, a.replace(r"f_{rr}+\frac{1}{r}f_r+\frac{1}{r^2}",r"f_{rr}+\frac{1}{r^2}").replace(r"r^2 f_{rr}+r f_r+f_{\theta\theta}",r"r^2 f_{rr}+f_{\theta\theta}"))
        truth = json.loads((ROOT/"examples/expected.json").read_text())
        for variant in ("correct", "mistake"):
            parsed = extract((ROOT/f"examples/laplacian_{variant}.tex").read_text())
            self.assertEqual(len(parsed["equations"]), 12)
            self.assertEqual([(p['before'],p['after']) for p in parsed['pairs']], [(p['before'],p['after']) for p in truth['variants'][variant]])
        self.assertEqual(truth['variants']['mistake'][-2]['expected'], 'incorrect')
        self.assertEqual(truth['variants']['mistake'][-1]['expected'], 'correct')

    def test_response_validation_and_threshold(self):
        for choice in judge.CRITERIA:
            self.assertEqual(judge.validate_answer(answer(choice))["verdict"], choice)
        result = judge.validate_answer(answer("incorrect", {"correct":.2,"incorrect":.7,"uncertain":.1}))
        self.assertEqual(result["verdict"], "uncertain")
        self.assertEqual(result["raw_choice"], "incorrect")
        self.assertEqual(judge.validate_answer(answer("incorrect", {"correct":.1,"incorrect":.8,"uncertain":.1}))["verdict"], "incorrect")
        for bad in ({}, {"answers":[]}, answer("unknown"), answer("correct", {"correct":float('nan'),"incorrect":0,"uncertain":0}), answer("correct", {"correct":.1,"incorrect":.8,"uncertain":.1})):
            with self.subTest(bad=bad), self.assertRaises(judge.JudgeError):
                judge.validate_answer(bad)

    @patch.dict(os.environ, {"TYPESAFE_API_KEY":"unit-test-placeholder"})
    def test_http_failures_and_retry(self):
        with patch.dict(os.environ,{'TYPESAFE_API_KEY':'secret\nvalue'}), self.assertRaises(judge.JudgeError) as error:
            judge.call_jev({})
        self.assertNotIn('secret',str(error.exception))
        for failure in (TimeoutError(), urllib.error.URLError("unreachable"), urllib.error.HTTPError(judge.ENDPOINT,401,"Unauthorized",{},None)):
            opener = Mock(); opener.open.side_effect = failure
            with patch("urllib.request.build_opener",return_value=opener), self.assertRaises(judge.JudgeError) as error:
                judge.call_jev({})
            self.assertNotIn("unit-test-placeholder",str(error.exception))
        stream = io.BytesIO(json.dumps(answer()).encode())
        opener = Mock(); opener.open.side_effect = [urllib.error.HTTPError(judge.ENDPOINT,429,"limit",{},None),stream]
        with patch("urllib.request.build_opener",return_value=opener), patch("time.sleep"):
            self.assertEqual(judge.call_jev({})["verdict"], "correct")
        self.assertEqual(opener.open.call_count,2)
        with patch("urllib.request.build_opener") as make:
            make.return_value.open.return_value = io.BytesIO(b'not JSON')
            with self.assertRaises(judge.JudgeError): judge.call_jev({})

    def test_payload_does_not_include_oracle_or_filename(self):
        parsed = extract((ROOT/"examples/laplacian_mistake.tex").read_text())
        payload = judge.payload_for(parsed["equations"], parsed["pairs"][-2], "r>0", judge.DEFAULT_MODEL)
        text = json.dumps(payload)
        for forbidden in ("laplacian_mistake", "expected", "explanation", "TYPESAFE_API_KEY", "locations"):
            self.assertNotIn(forbidden,text)
        self.assertEqual(payload['state']['before'],parsed['equations'][9]['latex'])
        with patch.dict(os.environ,{"TYPESAFE_API_KEY":"not-for-tex","OTHER_API_TOKEN":"not-for-tex"}):
            self.assertNotIn("TYPESAFE_API_KEY",tex_environment())
            self.assertNotIn("OTHER_API_TOKEN",tex_environment())
        self.assertIsNone(judge.NoRedirect().redirect_request(None,None,302,'',{},'https://example.org'))

    def test_api_boundaries_and_invalid_pairs(self):
        with TestClient(web.app, base_url='http://127.0.0.1') as client, patch.dict(os.environ,{"TYPESAFE_API_KEY":""}):
            self.assertEqual(client.get('/api/status').json()['api_key_configured'],False)
            self.assertEqual(client.post('/api/documents',json={'name':'a.tex','source':'x'}).status_code,403)
            self.assertEqual(client.get('/api/status',headers={'Host':'evil.test'}).status_code,403)
            self.assertEqual(client.post('/api/documents',headers={'X-JevTex-Client':'1','Origin':'https://evil.test'},json={}).status_code,403)
            self.assertEqual(client.get('/api/documents/not-an-id/pdf').status_code,404)
        with tempfile.TemporaryDirectory() as directory, patch.object(web,'DATA',Path(directory)), TestClient(web.app, base_url='http://127.0.0.1') as client:
            headers={'X-JevTex-Client':'1'}
            with patch.object(web,'compile_tex',side_effect=ValueError('missing TeX')):
                response=client.post('/api/documents',headers=headers,json={'name':'x.tex','source':r'\begin{document}\[a=b\]\[b=c\]\end{document}'})
            doc=response.json(); self.assertFalse(doc['pdf_available']); self.assertEqual(len(doc['equations']),2)
            url=f"/api/documents/{doc['id']}/check"
            with patch.dict(os.environ,{'TYPESAFE_API_KEY':''}):
                self.assertEqual(client.post(url,headers=headers,json={'pairs':doc['pairs']}).status_code,503)
            with patch.dict(os.environ,{'TYPESAFE_API_KEY':'test-placeholder'}), patch.object(judge,'call_jev',return_value=judge.validate_answer(answer())) as call:
                for pair in [{'before':'missing','after':'e2'},{'before':'e1','after':'e1'}]:
                    self.assertEqual(client.post(url,headers=headers,json={'pairs':[pair]}).status_code,422)
                call.assert_not_called()
                changed={'before':'e2','after':'e1','context_ids':[]}
                checked=client.post(url,headers=headers,json={'pairs':[changed],'assumptions':'test'}).json()
                self.assertEqual(checked['results'][0]['before'],'e2')
                self.assertEqual(call.call_args[0][0]['state']['before'],'b=c')


@unittest.skipUnless(os.environ.get('JEVTEX_INTEGRATION') == '1','JEVTEX_INTEGRATION=1 enables real TeX/PDF checks')
class PdfIntegration(unittest.TestCase):
    def test_compile_mapping_and_annotation_api(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(web,'DATA',Path(folder)), TestClient(web.app, base_url='http://127.0.0.1') as client:
            truth=json.loads((ROOT/'examples/expected.json').read_text())
            headers={'X-JevTex-Client':'1'}
            for variant in ('correct','mistake'):
                source=(ROOT/f'examples/laplacian_{variant}.tex').read_text()
                doc=client.post('/api/documents',headers=headers,json={'name':f'{variant}.tex','source':source}).json()
                self.assertTrue(doc['pdf_available'],doc['warnings'])
                self.assertEqual(doc['warnings'],[])
                self.assertTrue(all(e['locations'] for e in doc['equations']))
                # Regression: align's first row must not map to the preceding prose.
                self.assertGreater(doc['equations'][1]['locations'][0]['rect'][1],doc['equations'][2]['locations'][0]['rect'][3])
                self.assertEqual(doc['equations'][10]['locations'][0]['page'],2)
                raw=client.get(f"/api/documents/{doc['id']}/pdf").content
                results=[judge.validate_answer(answer(p['expected'])) for p in truth['variants'][variant]]
                with patch.dict(os.environ,{'TYPESAFE_API_KEY':'integration-placeholder'}),patch.object(judge,'call_jev',side_effect=results):
                    checked=client.post(f"/api/documents/{doc['id']}/check",headers=headers,json={'pairs':doc['pairs'],'assumptions':truth['assumptions']}).json()
                self.assertEqual([r['verdict'] for r in checked['results']],[p['expected'] for p in truth['variants'][variant]])
                annotated=PdfReader(io.BytesIO(client.get(f"/api/documents/{doc['id']}/pdf?annotated=true").content))
                self.assertEqual(len(annotated.pages),2)
                annotations=[a.get_object() for page in annotated.pages for a in page.get('/Annots',[])]
                self.assertEqual(len(annotations),int(variant=='mistake'))
                if annotations:
                    self.assertIn('/AP',annotations[0]); self.assertEqual(annotations[0]['/C'],[1,0,0])
                    self.assertEqual(list(annotations[0]['/Rect']),doc['equations'][10]['locations'][0]['rect'])
                self.assertEqual(client.get(f"/api/documents/{doc['id']}/pdf").content,raw)
                self.assertNotIn('integration-placeholder',client.get(f"/api/documents/{doc['id']}/results").text)


if __name__ == '__main__':
    unittest.main()
