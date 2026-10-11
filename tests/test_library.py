"""Synthetic documents are isolated temporary test fixtures, never library seed data."""
import io
import json
import re
from pathlib import Path

import fitz
import pytest
from app import create_app
from biology.library import Library, metadata


def make_pdf(path, bodies, component='12'):
    with fitz.open() as doc:
        for n,body in enumerate(bodies):
            page=doc.new_page()
            page.insert_text((72,45),f'TEST FIXTURE 9700/{component} - not an actual exam')
            page.insert_text((72,90),body,fontsize=11)
        doc.save(path)
    return path


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path/'library')


@pytest.mark.parametrize('name,expected',[
    ('9700_s24_qp_12.pdf',(2024,'s','qp',1,2)),
    ('9700_M26_MS_42.PDF',(2026,'m','ms',4,2)),
    ('9700_w19_er.pdf',(2019,'w','er',0,0)),
    ('9700_s23_12_qp.pdf',(2023,'s','qp',1,2)),
    ('9700_s23_00_gt.pdf',(2023,'s','gt',0,0)),
])
def test_metadata(name,expected):
    m=metadata(name)
    assert tuple(m[k] for k in ('year','season','kind','paper','variant'))==expected


@pytest.mark.parametrize('name',['0610_s24_qp_12.pdf','9700_s27_qp_12.pdf','9700_s15_qp_12.pdf','9700_x24_qp_12.pdf','9700_s24_qp.pdf','9700_s24_qp_72.pdf'])
def test_metadata_reject(name):
    with pytest.raises(ValueError):metadata(name)


def test_import_dedup_provenance_and_conflict(lib,tmp_path):
    path=make_pdf(tmp_path/'9700_s24_qp_12.pdf',['Mitochondria provide energy for cellular respiration and active transport.'])
    first=lib.import_pdf(path,source='one',url='https://example.com/one')
    second=lib.import_pdf(path,source='two',url='https://example.com/two')
    assert first['id']==second['id'] and second['duplicate']
    with lib.connect() as db:
        assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM sources').fetchone()[0]==2
    path.unlink()
    make_pdf(path,['Different PDF content must never replace an existing examination document.'])
    with pytest.raises(ValueError,match='同名异内容'):lib.import_pdf(path)
    assert len(list((lib.home/'quarantine').iterdir()))==1


def test_page_search_highlight_and_filters(lib,tmp_path):
    path=make_pdf(tmp_path/'9700_s24_qp_12.pdf',['Welcome to this isolated test fixture for the local biology library.', 'The mitochondria release energy during cellular respiration and active transport.'])
    lib.import_pdf(path)
    found=lib.search('mitochondria',{'year':'2024','season':'s','paper':'1','variant':'2','kind':'qp'})
    assert found['total']==1 and found['items'][0]['hit_page']==2
    assert found['items'][0]['label'] is None
    assert '<mark>mitochondria</mark>' in found['items'][0]['snippet_html']
    assert lib.search('mitochondria',{'year':2025})['total']==0
    assert lib.search('" OR * --')['total']==0
    assert lib.search('<script>')['total']==0
    assert lib.search('')['total']==1


def test_manual_cross_page_subquestion_ms_and_reindex(lib,tmp_path):
    qp=lib.import_pdf(make_pdf(tmp_path/'9700_s24_qp_12.pdf',[
        'Chloroplasts absorb light to begin photosynthesis and produce energy. Uniquealpha',
        'Uniquebeta continues the same question across two PDF pages for testing.']))
    ms=lib.import_pdf(make_pdf(tmp_path/'9700_s24_ms_12.pdf',['Mark scheme for photosynthesis gives credit for light absorption in chloroplasts.']))
    span={'label':'1(a)(ii)','page_start':1,'line_start':2,'page_end':2,'line_end':2,'ms_doc_id':ms['id'],'ms_page':1}
    lib.correct(qp['id'],[span])
    result=lib.search('Uniquealpha Uniquebeta',{'kind':'qp'})
    assert result['total']==1
    hit=result['items'][0]
    assert hit['label']=='1(a)(ii)' and hit['page_end']==2 and hit['ms_doc_id']==ms['id']
    assert lib.search('Uniquealpha TEST',{'kind':'qp'})['total']==1
    lib.index_document(qp['id'])
    assert lib.search('Uniquealpha Uniquebeta')['items'][0]['confidence']=='manual'
    with pytest.raises(ValueError):lib.correct(qp['id'],[span,span])
    with pytest.raises(ValueError):lib.correct(qp['id'],[{**span,'ms_page':999}])


def test_correct_ms_variant_only(lib,tmp_path):
    qp=lib.import_pdf(make_pdf(tmp_path/'9700_s24_qp_12.pdf',['A long enough sample question about aerobic respiration and the release of energy.']))
    ms=lib.import_pdf(make_pdf(tmp_path/'9700_s24_ms_13.pdf',['Different variant mark scheme must not be associated with this question paper.'],component='13'))
    assert not lib.related(lib.document(qp['id']))
    with pytest.raises(ValueError,match='不属于'):
        lib.correct(qp['id'],[{'label':'1','page_start':1,'page_end':1,'ms_doc_id':ms['id'],'ms_page':1}])


def test_scanned_pdf_not_indexed(lib,tmp_path):
    source=fitz.open();p=source.new_page();p.insert_text((72,90),'Scanned mitochondria cellular respiration text has no embedded text layer.')
    png=p.get_pixmap().tobytes('png')
    path=tmp_path/'9700_s24_qp_12.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page();page.insert_image(page.rect,stream=png);pdf.save(path)
    result=lib.import_pdf(path)
    assert result['status']=='needs_ocr'
    assert lib.search('mitochondria')['total']==0
    assert lib.document(result['id'])['searchable_pages']==0


def test_invalid_pdf_no_record(lib,tmp_path):
    path=tmp_path/'9700_s24_qp_12.pdf';path.write_text('<html>login required</html>')
    with pytest.raises(Exception):lib.import_pdf(path)
    assert lib.search()['total']==0


def test_header_date_mismatch_rejected(lib,tmp_path):
    path=make_pdf(tmp_path/'9700_s24_qp_12.pdf',['May/June 2025. This test file is deliberately misnamed to check date validation.'])
    with pytest.raises(ValueError,match='年份或考季'):lib.import_pdf(path)


def test_reindex_retains_successful_ocr(lib,tmp_path):
    source=fitz.open();p=source.new_page();p.insert_text((72,90),'Image test fixture about respiration and mitochondria.')
    path=tmp_path/'9700_s24_qp_12.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page();page.insert_image(page.rect,stream=p.get_pixmap().tobytes('png'));pdf.save(path)
    result=lib.import_pdf(path)
    text='Previously recognised OCR text about mitochondria and cellular respiration.'
    with lib.connect() as db:
        db.execute("UPDATE pages SET status='ocr',text=?,lines_json=? WHERE doc_id=?",(text,json.dumps([{'text':text,'x':0,'y':0,'bold':False}]),result['id']))
    lib.index_document(result['id'])
    assert lib.search('mitochondria')['total']==1
    assert lib.document(result['id'])['status']=='ready'


def test_blank_answer_space_and_turnover_not_ocr(lib,tmp_path):
    path=tmp_path/'9700_s24_qp_12.pdf'
    with fitz.open() as pdf:
        p=pdf.new_page();p.insert_text((72,90),'9700/12 Test fixture about mitochondria and cell transport with enough searchable text.')
        p=pdf.new_page();p.insert_text((72,420),'Question 2 starts on page 3');p.insert_text((72,799),'Copyright 2024 9700/12')
        p=pdf.new_page();p.insert_text((72,90),'........................................');p.insert_text((72,799),'Copyright 2024 9700/12')
        pdf.save(path)
    result=lib.import_pdf(path)
    assert result['status']=='ready'
    with lib.connect() as db:
        assert [r[0] for r in db.execute('select status from pages order by page')]==['text','blank','blank']


def test_auto_question_sequence(lib,tmp_path):
    path=tmp_path/'9700_s24_qp_22.pdf'
    with fitz.open() as pdf:
        p=pdf.new_page();p.insert_text((72,90),'9700/22 TEST FIXTURE This document tests automatic question boundary detection.')
        p=pdf.new_page();p.insert_text((49,90),'1 Explain the function of mitochondria during cellular respiration and energy release.')
        p=pdf.new_page();p.insert_text((72,90),'Continued respiration question with another keyword uniquecontinuation.')
        p.insert_text((49,290),'2 Describe the structure of chloroplasts in a photosynthetic plant cell.')
        pdf.save(path)
    result=lib.import_pdf(path)
    hit=lib.search('uniquecontinuation')['items'][0]
    assert hit['label']=='1' and hit['page_start']==2 and hit['page_end']==3 and hit['hit_page']==3
    assert lib.search('chloroplasts')['items'][0]['label']=='2'


def test_routes_upload_range_csrf_and_viewer(tmp_path):
    app=create_app(tmp_path/'data');app.config['TESTING']=True
    client=app.test_client()
    for url in ['/','/coverage','/import','/health','/api/search','/?q=mitochondria']:
        assert client.get(url).status_code==200
    with client.session_transaction() as s: token=s['csrf']
    path=make_pdf(tmp_path/'9700_s24_qp_12.pdf',['Mitochondria are the site of aerobic respiration and supply energy to the cell.'])
    assert client.post('/api/import').status_code==403
    for duplicate in [False,True]:
        r=client.post('/api/import',headers={'X-CSRF-Token':token},data={'files':(io.BytesIO(path.read_bytes()),path.name)})
        assert r.status_code==200
        item=r.json['items'][0];assert item['duplicate']==duplicate
    docid=item['id']
    for url in [f'/document/{docid}',f'/viewer/{docid}?page=1',f'/page/{docid}/1.png']:
        assert client.get(url).status_code==200
    pdf=client.get(f'/pdf/{docid}',headers={'Range':'bytes=0-9'})
    assert pdf.status_code==206 and pdf.data.startswith(b'%PDF')
    assert client.get(f'/viewer/{docid}?page=2').status_code==404
    assert client.get('/?q=mitochondria').status_code==200
    assert client.get('/api/search?q=mitochondria').json['items'][0]['hit_page']==1
    assert client.post(f'/api/document/{docid}/corrections',headers={'X-CSRF-Token':token},json=[]).status_code==200
    assert client.get('/health',headers={'Host':'untrusted.example'}).status_code==400


def test_coverage_has_all_years_and_page_pagination(lib,tmp_path):
    for component in ['12','13']:
        lib.import_pdf(make_pdf(tmp_path/f'9700_s24_qp_{component}.pdf',['Cellular respiration and mitochondria release chemical energy for transport.'],component))
    assert [x['year'] for x in lib.coverage()]==list(range(2016,2027))
    assert lib.coverage()[8]['qp']==2 and lib.coverage()[10]['files']==0
    p1=lib.search('mitochondria',size=1,page=1);p2=lib.search('mitochondria',size=1,page=2)
    assert p1['pages']==2 and p1['items'][0]['id']!=p2['items'][0]['id']
