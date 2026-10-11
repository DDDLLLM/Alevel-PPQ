from pathlib import Path
import json
import pytest
from biology.library import Library
from biology.sources import Client, SourceBlocked, discover_fraft, discover_papersc, discover_html, fraft_download_url


def test_fraft_current_browser_confirmed_route():
    assert fraft_download_url('9700_s24_qp_23.pdf') == 'https://cie.fraft.cn/obj/Common/Fetch/redir/9700_s24_qp_23.pdf'
    with pytest.raises(ValueError):
        fraft_download_url('../9700_s24_qp_23.pdf')
    with pytest.raises(ValueError):
        fraft_download_url('0610_s24_qp_23.pdf')


def test_fraft_search_uses_current_route_and_validates_catalog(tmp_path):
    lib = Library(tmp_path)
    class ListingClient:
        def __init__(self): self.calls = []
        def json(self, url, form):
            self.calls.append((url, form))
            season = {'Mar':'m', 'Jun':'s', 'Nov':'w'}[form['season']]
            return {'total': 1, 'rows': [{'file':f'9700_{season}23_qp_12.pdf'}]}
    client = ListingClient()
    assert discover_fraft(lib, client, [2023]) == 3
    assert all(url == 'https://cie.fraft.cn/obj/Common/Fetch/renum' for url, form in client.calls)
    with lib.connect() as db:
        row = db.execute("SELECT url FROM catalog WHERE filename='9700_s23_qp_12.pdf'").fetchone()
        assert row[0] == 'https://cie.fraft.cn/obj/Common/Fetch/redir/9700_s23_qp_12.pdf'
    assert lib.search()['total'] == 0


class FakeClient:
    def __init__(self,data):self.data=data
    def json(self,*args):return self.data
    def text(self,*args):return self.data


def test_fraft_rejects_truncated_listing(tmp_path):
    with pytest.raises(SourceBlocked,match='截断'):
        discover_fraft(Library(tmp_path),FakeClient({'total':2,'rows':[{'file':'9700_m26_qp_12.pdf'}]}),[2026])


def test_papersc_rejects_schema_change(tmp_path):
    with pytest.raises(SourceBlocked):discover_papersc(Library(tmp_path),FakeClient({'results':[]}),[2023])


def test_html_only_records_matching_actual_links(tmp_path):
    lib=Library(tmp_path)
    c=FakeClient('<a href="9700_s24_qp_12.pdf">PDF</a><a href="0610_s24_qp_12.pdf">Other</a>')
    assert discover_html(lib,c,'https://example.org/list/')==1
    assert lib.search()['total']==0
    with lib.connect() as db:
        assert db.execute('SELECT url FROM catalog').fetchone()[0]=='https://example.org/list/9700_s24_qp_12.pdf'


def test_robots_disallow_respected(tmp_path,monkeypatch):
    client=Client(tmp_path)
    class Response:
        status_code=200
        headers={'Content-Type':'text/plain'}
        content=b'User-agent: *\nDisallow: /doc/'
        text=content.decode()
    monkeypatch.setattr(client,'_request',lambda *a,**k:Response())
    with pytest.raises(SourceBlocked):client.allowed('https://example.org/doc/123')
    client.allowed('https://example.org/search/')


def test_pdf_resumes_validated_partial(tmp_path,monkeypatch):
    import fitz,requests
    with fitz.open() as pdf:
        p=pdf.new_page();p.insert_text((72,90),'Isolated PDF fixture to test network byte range integrity.')
        raw=pdf.tobytes()
    c=Client(tmp_path)
    split=len(raw)//2
    calls=[]
    class Response:
        def __init__(self,n):
            self.n=n;self.status_code=200 if n==0 else 206
            self.headers={'ETag':'"stable"','Content-Length':str(len(raw) if n==0 else len(raw)-split)}
            if n:self.headers['Content-Range']=f'bytes {split}-{len(raw)-1}/{len(raw)}'
        def iter_content(self,*a):
            if self.n==0:
                yield raw[:split]
                raise requests.ConnectionError('Interrupted download')
            yield raw[split:]
        def close(self):pass
    def request(*a,**kw):
        calls.append(kw['headers']);return Response(len(calls)-1)
    monkeypatch.setattr(c,'request',request)
    monkeypatch.setattr('biology.sources.time.sleep',lambda n:None)
    result=c.pdf('https://example.org/paper.pdf')
    assert result.read_bytes()==raw
    assert calls[1]=={'Range':f'bytes={split}-','If-Range':'"stable"'}
    assert c.pdf('https://example.org/paper.pdf')==result and len(calls)==2


@pytest.mark.parametrize('retry',['120','Wed, 01 Jan 2098 00:00:00 GMT'])
def test_long_retry_after_stops_without_early_retry(tmp_path,monkeypatch,retry):
    c=Client(tmp_path);calls=[]
    class Response:
        status_code=429
        headers={'Retry-After':retry}
        def close(self):pass
    def request(*a,**kw):calls.append(1);return Response()
    monkeypatch.setattr(c.session,'request',request)
    monkeypatch.setattr('biology.sources.time.sleep',lambda n:None)
    with pytest.raises(SourceBlocked,match='不提前重试'):
        c._request('GET','https://example.org/test')
    assert calls==[1]
