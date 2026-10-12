from biology.library import Library
from manage import main


def test_ocr_year_scope_and_resume_exclude_unrequested_documents(tmp_path,monkeypatch):
    lib=Library(tmp_path)
    with lib.connect() as db:
        for i,(year,status) in enumerate([(2021,'partial'),(2022,'ready'),(2022,'partial'),(2026,'needs_ocr')],1):
            db.execute('INSERT INTO documents(id,filename,sha256,year,season,kind,paper,variant,status) VALUES(?,?,?,?,?,?,?,?,?)',
                       (i,f'9700_s{year%100:02}_qp_{10+i}.pdf',str(i),year,'s','qp',1,i,status))
    calls=[]
    monkeypatch.setattr(Library,'index_document',lambda self,doc_id,ocr=False:calls.append((doc_id,ocr)))
    assert main(['--data',str(tmp_path),'reindex','--years','2022:2026','--ocr'])==0
    assert calls==[(2,True),(3,True),(4,True)]
    calls.clear()
    assert main(['--data',str(tmp_path),'reindex','--years','2022:2026','--ocr','--pending-only'])==0
    assert calls==[(3,True),(4,True)]
