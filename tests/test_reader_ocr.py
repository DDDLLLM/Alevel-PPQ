"""Actual Tesseract verification on an isolated image-only fixture, never seed data."""
import shutil

import fitz
import pytest
from biology.library import Library
from biology.reader import Reader


@pytest.mark.skipif(not shutil.which('tesseract'),reason='Requires local Tesseract eng')
def test_image_only_ocr_coordinates_preserve_search_text(tmp_path):
    file=tmp_path/'9700_s24_qp_22.pdf'
    with fitz.open() as src:
        p=src.new_page()
        p.insert_text((72,90),'Scanned TEST FIXTURE about mitochondria and respiration.\nCells release chemical energy to power active transport.\nThis image has no original embedded text.',fontsize=15)
        png=p.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes('png')
    with fitz.open() as dst:
        p=dst.new_page();p.insert_image(p.rect,stream=png);dst.save(file)
    lib=Library(tmp_path/'db');d=lib.import_pdf(file)
    assert d['status']=='needs_ocr'
    with fitz.open(lib.pdf_path(lib.document(d['id']))) as pdf:assert not pdf[0].get_text('words')
    lib.index_document(d['id'],ocr=True)
    r=Reader(lib);before=r.layout(d['id'],1)
    assert before['needs_coordinates'] and 'mitochondria' in before['text']
    after=r.layout(d['id'],1,repair=True)
    assert after['source']=='ocr' and not after['needs_coordinates']
    assert any(w['text']=='mitochondria' for w in after['words'])
    assert all(0<=w['box'][0]<w['box'][2]<=after['width'] and 0<=w['box'][1]<w['box'][3]<=after['height'] for w in after['words'])
    assert after['text']==before['text']
    assert lib.search('mitochondria')['total']==1
    assert r.layout(d['id'],1)==after
