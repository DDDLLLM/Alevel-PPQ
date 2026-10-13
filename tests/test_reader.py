"""Reader regressions; generated fixtures remain inside pytest temp directories."""
import json
import sqlite3

import fitz
import pytest
from biology.library import Library
from biology.reader import Reader
from app import create_app
from test_library import make_pdf


def test_additive_migration_backup_preserves_original_tables(tmp_path):
    lib=Library(tmp_path/'db')
    result=lib.import_pdf(make_pdf(tmp_path/'9700_s24_qp_12.pdf',['Mitochondria and aerobic respiration provide energy for active transport in living cells.']))
    lib.correct(result['id'],[dict(label='1(a)',page_start=1,page_end=1,line_start=2,line_end=2)])
    with lib.connect() as db:
        original={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in ('documents','pages','units','corrections')}
        db.executescript('DROP TABLE page_layouts; DROP TABLE answer_links; DROP TABLE answer_directories; PRAGMA user_version=1;')
    lib=Library(lib.home)
    assert len(list((lib.home/'backups').glob('before-reader-v2-*.sqlite3')))==1
    Library(lib.home)
    assert len(list((lib.home/'backups').iterdir()))==1
    with lib.connect() as db:
        for t,rows in original.items():assert [tuple(r) for r in db.execute('SELECT * FROM '+t)]==rows
        assert db.execute('PRAGMA user_version').fetchone()[0]==2
    with sqlite3.connect(next((lib.home/'backups').iterdir())) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==1


def test_manual_cross_page_subanswer_survives_reindex_and_rejects_wrong_variant(tmp_path):
    lib=Library(tmp_path/'db');r=Reader(lib)
    qp=lib.import_pdf(make_pdf(tmp_path/'9700_s24_qp_22.pdf',['Describe respiration and mitochondria with enough searchable text for this question.'],'22'))
    ms=lib.import_pdf(make_pdf(tmp_path/'9700_s24_ms_22.pdf',['First part of this answer about respiration includes electron carriers and energy transfer.','The answer continues with oxidative phosphorylation and chemiosmosis for ATP production.'],'22'))
    wrong=lib.import_pdf(make_pdf(tmp_path/'9700_s24_ms_23.pdf',['Wrong variant must never match this question paper with the same year and season.'],'23'))
    payload=dict(label='4(a)(iii)',ms_doc_id=ms['id'],ranges=[dict(page=n,box=[0,65,595,300]) for n in [1,2]])
    a=r.save_link(qp['id'],payload)
    assert a['status']=='manual' and a['complete'] and len(a['segments'])==2 and 'chemiosmosis' in a['text']
    lib.index_document(qp['id']);lib.index_document(ms['id'])
    assert r.resolve(qp['id'],'4 (a) (iii)')['text']==a['text']
    assert r.resolve(qp['id'],'4(b)(ii)')['status']=='unlocated'
    with pytest.raises(ValueError,match='完整组件'):r.save_link(qp['id'],dict(payload,ms_doc_id=wrong['id']))
    with pytest.raises(ValueError,match='范围'):r.save_link(qp['id'],dict(payload,ranges=[dict(page=1,box=[0,20,9999,30])]))
    with pytest.raises(ValueError):r.save_link(qp['id'],dict(payload,ranges=[dict(page=1,box=[0,float('nan'),200,300])]))


def table_pdf(path):
    with fitz.open() as pdf:
        for rows in [[('4(a)(iii)','Ester bonds join fatty acids to glycerol and form triglycerides.')],[('4(a)(iii)','Continued answer includes condensation and the release of water.'),('4(b)(ii)','Phospholipids have hydrophilic heads and hydrophobic tails.')]]:
            p=pdf.new_page(width=842,height=595)
            p.insert_text((65,35),'TEST FIXTURE 9700/22')
            for x,t in [(65,'Question'),(400,'Answer'),(750,'Marks')]:p.insert_text((x,65),t)
            for i,(k,t) in enumerate(rows):
                y=90+i*150;p.insert_text((75,y),k);p.insert_text((160,y),t);p.insert_text((755,y),'2')
                p.draw_rect(fitz.Rect(62,y+120,785,y+121),color=None,fill=(0,0,0))
        pdf.save(path)
    return path


def test_auto_table_repeated_subquestion_across_pages_and_missing_label(tmp_path):
    lib=Library(tmp_path/'db');r=Reader(lib)
    ms=lib.import_pdf(table_pdf(tmp_path/'9700_s24_ms_22.pdf'))
    d=r.directory(ms['id'])['entries']
    assert d['4(a)(iii)']['complete'] and len(d['4(a)(iii)']['segments'])==2
    assert 'water' in d['4(a)(iii)']['segments'][1]['text']
    assert 'Phospholipids' not in d['4(a)(iii)']['segments'][1]['text']
    assert len(d['4']['segments'])==3
    assert '4(a)(ii)' not in d


def test_rotated_native_layout_and_read_api_validation(tmp_path):
    path=tmp_path/'9700_s24_ms_22.pdf'
    with fitz.open() as p:
        pg=p.new_page();pg.insert_text((72,90),'Mitochondria provide chemical energy for active transport and cellular respiration.');pg.set_rotation(90);p.save(path)
    app=create_app(tmp_path/'db');lib=app.config['LIBRARY'];doc=lib.import_pdf(path);client=app.test_client()
    layout=client.get(f'/api/reader/{doc["id"]}/page/1').json
    assert layout['width']==842 and layout['height']==595
    assert all(0<=w['box'][0]<w['box'][2]<=842 and 0<=w['box'][1]<w['box'][3]<=595 for w in layout['words'])
    assert client.get(f'/api/reader/{doc["id"]}/page/99').status_code==400
    assert client.post(f'/api/reader/{doc["id"]}/page/1/coordinates').status_code==403
    assert client.get(f'/api/reader/{doc["id"]}/find?q=mitochondria').json['items'][0]['page']==1
    assert client.get('/api/search?component=999').status_code==400


def test_component_buttons_include_actual_variant_eight_and_no_main_selects(tmp_path):
    app=create_app(tmp_path/'db');lib=app.config['LIBRARY']
    lib.import_pdf(make_pdf(tmp_path/'9700_w25_qp_38.pdf',['Active transport and cellular respiration are biological processes in this example fixture.'],'38'))
    client=app.test_client();r=client.get('/?year=2025&season=w&component=38&q=transport')
    assert r.status_code==200 and b'>38</a>' in r.data and b'w25' in r.data
    assert b'<select' not in r.data
    assert client.get('/api/search?q=transport&year=2025&season=w&component=38').json['total']==1
    assert client.get('/api/search?q=transport&component=33').json['total']==0
    assert client.get('/api/search?q=transport&season=s&component=38').json['total']==0


def test_legacy_manual_page_is_not_promoted_to_full_answer(tmp_path):
    lib=Library(tmp_path/'db');r=Reader(lib)
    qp=lib.import_pdf(make_pdf(tmp_path/'9700_s24_qp_22.pdf',['Mitochondria release chemical energy during aerobic respiration and active transport.'],'22'))
    ms=lib.import_pdf(table_pdf(tmp_path/'9700_s24_ms_22.pdf'))
    lib.correct(qp['id'],[dict(label='4(a)(iii)',page_start=1,page_end=1,line_start=2,line_end=2,ms_doc_id=ms['id'],ms_page=2)])
    a=r.resolve(qp['id'],'4(a)(iii)')
    assert a['status']=='manual' and a['page']==2 and not a['complete'] and not a['text']


def test_subquestion_boundaries_derive_from_main_directory(tmp_path):
    lib=Library(tmp_path/'db');path=tmp_path/'9700_s24_qp_22.pdf'
    with fitz.open() as pdf:
        p=pdf.new_page();p.insert_text((72,90),'9700/22 Test fixture checking actual layout-based subquestion boundaries.')
        p=pdf.new_page();p.insert_text((49,90),'1');p.insert_text((72,90),'(a) Describe the structure of mitochondria and the roles of organelles in the cell.')
        p.insert_text((72,190),'(b) Explain the following processes in the living cell for this example question.')
        p.insert_text((96,250),'(i) State the role of the membrane in active transport and diffusion of molecules.')
        p=pdf.new_page();p.insert_text((96,90),'(ii) Describe photosynthesis and the importance of carbon fixation in plants.')
        p.insert_text((49,290),'2');p.insert_text((72,290),'State why respiration provides energy for important cellular processes.')
        pdf.save(path)
    qp=lib.import_pdf(path);r=Reader(lib)
    assert r.question(qp['id'],'1(b)')['page_end']==3
    part=r.question(qp['id'],'1(b)(ii)')
    assert part['page']==3 and part['complete'] and 'photosynthesis' in part['text'] and 'provides energy' not in part['text']
    assert not r.question(qp['id'],'1(b)(iii)')['complete']


def test_failed_coordinate_repair_keeps_saved_ocr_and_index(tmp_path,monkeypatch):
    lib=Library(tmp_path/'db');path=tmp_path/'9700_s24_qp_22.pdf'
    with fitz.open() as src:
        pg=src.new_page();pg.insert_text((72,90),'Image-only sample for checking retention of previously successful OCR text.')
        png=pg.get_pixmap().tobytes('png')
    with fitz.open() as pdf:
        p=pdf.new_page();p.insert_image(p.rect,stream=png);pdf.save(path)
    doc=lib.import_pdf(path);text='Saved OCR about mitochondria, respiration and transport must remain available.'
    with lib.connect() as db:
        db.execute("UPDATE pages SET text=?,lines_json=?,status='ocr' WHERE doc_id=?",(text,json.dumps([dict(text=text,x=0,y=0,bold=False)]),doc['id']))
    lib.index_document(doc['id'])
    r=Reader(lib);assert r.layout(doc['id'],1)['needs_coordinates']
    def failed(*args,**kwargs):raise RuntimeError('test: unavailable eng language data')
    monkeypatch.setattr(fitz.Page,'get_textpage_ocr',failed)
    with pytest.raises(ValueError,match='已有 OCR'):r.layout(doc['id'],1,repair=True)
    assert r.layout(doc['id'],1)['text']==text
    assert lib.search('mitochondria')['total']==1
