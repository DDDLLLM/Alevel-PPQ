#!/usr/bin/env python3
"""Real-PDF acceptance in an isolated temporary database; prints an auditable report."""
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from app import create_app
from biology.library import Library

def run():
    source=Library()
    with source.connect() as db:
        qp=dict(db.execute("SELECT * FROM documents WHERE filename='9700_m16_qp_12.pdf'").fetchone())
        ms=dict(db.execute("SELECT * FROM documents WHERE filename='9700_m16_ms_12.pdf'").fetchone())
    with tempfile.TemporaryDirectory() as folder:
        app=create_app(folder);app.config['TESTING']=True
        client=app.test_client();client.get('/')
        with client.session_transaction() as s:token=s['csrf']
        for d in (qp,ms):
            r=client.post('/api/import',headers={'X-CSRF-Token':token},data={'files':(io.BytesIO(source.pdf_path(d).read_bytes()),d['filename'])})
            assert r.status_code==200 and not r.json['items'][0]['duplicate']
        lib=app.config['LIBRARY']
        assert lib.search(filters={'year':2016,'season':'m','kind':'qp'})['total']==1
        hit=lib.search('mitochondria',{'kind':'qp'})['items'][0]
        assert hit['hit_page']==6
        target=next(r for r in hit['related'] if r['kind']=='ms')
        assert target['filename']==ms['filename']
        with fitz.open(stream=client.get('/pdf/'+str(hit['id'])).data,filetype='pdf') as pdf:
            assert 'mitochondria' in pdf[5].get_text()
            assert '15' in pdf[5].get_text()
        rendered=client.get(f'/page/{hit["id"]}/6.png')
        assert rendered.status_code==200 and rendered.data[:8]==b'\x89PNG\r\n\x1a\n'
        assert client.get(f'/viewer/{hit["id"]}?page=6').status_code==200
        assert '9700_m16_qp_12.pdf' in client.get('/?year=2016&season=m&q=mitochondria').text
        rawms=client.get('/pdf/'+str(target['id']))
        assert rawms.status_code==200
        with fitz.open(stream=rawms.data,filetype='pdf') as pdf:
            assert '9700' in pdf[0].get_text() and '2016' in pdf[0].get_text()
        lib.correct(hit['id'],[{'label':'15','page_start':6,'line_start':36,'page_end':6,'line_end':51,'ms_doc_id':target['id'],'ms_page':2}])
        corrected=lib.search('mitochondria',{'kind':'qp'})['items'][0]
        assert corrected['label']=='15' and corrected['ms_page']==2
        r=client.post('/api/import',headers={'X-CSRF-Token':token},data={'files':(io.BytesIO(source.pdf_path(qp).read_bytes()),qp['filename'])})
        assert r.json['items'][0]['duplicate']
        assert lib.search()['total']==2
        lib.index_document(hit['id'])
        assert lib.search('mitochondria',{'kind':'qp'})['items'][0]['label']=='15'
        with lib.connect() as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print(json.dumps({'result':'PASS','real_qp':qp['filename'],'sha256':qp['sha256'],
            'keyword':'mitochondria','pdf_page':6,'confirmed_question':'15','linked_ms':ms['filename'],
            'confirmed_ms_page':2,'new_upload_visible':True,'duplicate_count_unchanged':True,
            'manual_correction_survives_reindex':True,'pdf_render_verified':True,
            'sqlite_integrity':'ok','test_database':'temporary, separate from user library'},ensure_ascii=False,indent=2))

if __name__=='__main__':run()
