import io
import json
import os
import secrets
import tempfile
from pathlib import Path

import fitz
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from biology.library import Library, SEASONS, TYPES, STATUSES
from biology.reader import Reader


def create_app(data_dir=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=256*1024*1024,
                      SESSION_COOKIE_SAMESITE='Strict', TRUSTED_HOSTS=['localhost','127.0.0.1','[::1]'])
    lib = Library(data_dir)
    app.config['LIBRARY'] = lib
    reader = Reader(lib)

    @app.before_request
    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(24)
        if request.method == 'POST' and not secrets.compare_digest(request.headers.get('X-CSRF-Token') or request.form.get('csrf',''), session['csrf']):
            abort(403, '请求校验失败，请刷新页面后重试')

    @app.context_processor
    def common():
        return dict(seasons=SEASONS, kinds=TYPES, statuses=STATUSES, csrf=session.get('csrf',''))

    @app.errorhandler(ValueError)
    def invalid(error):
        if request.path.startswith('/api/'):
            return jsonify(error=str(error)), 400
        return render_template('error.html', message=str(error)), 400

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error='单次上传不能超过 256 MB，请分批上传'), 413

    @app.errorhandler(404)
    def not_found(error):
        return render_template('error.html', message='找不到这个页面或文件'), 404

    @app.errorhandler(500)
    def server_error(error):
        message='处理失败，请稍后重试；详细原因已写入启动终端日志'
        if request.path.startswith('/api/'):
            return jsonify(error=message), 500
        return render_template('error.html', message=message), 500

    @app.get('/')
    def index():
        filters = {k:request.args.get(k,'qp' if k=='kind' else '') for k in ('year','season','paper','variant','component','kind','status')}
        if not filters['component'] and filters['paper'] and filters['variant']:
            filters['component'] = filters['paper'] + filters['variant']
        q = request.args.get('q','')
        data = lib.search(q,filters,request.args.get('page',1),phrase=request.args.get('mode')=='phrase')
        coverage = lib.coverage()
        def page_url(n):
            params = request.args.to_dict()
            params['page'] = n
            return url_for('index',**params)
        def filter_url(**changes):
            params = dict(filters, q=q, mode=request.args.get('mode','words'))
            params.update(changes)
            if 'component' in changes:
                params.pop('paper',None); params.pop('variant',None)
            return url_for('index', **{k:v for k,v in params.items() if v or k=='kind'})
        with lib.connect() as db:
            components = [str(r[0]) for r in db.execute('SELECT DISTINCT paper*10+variant FROM documents WHERE paper>0 ORDER BY 1')]
        return render_template('index.html', result=data, q=q, filters=filters,
            mode=request.args.get('mode','words'), page_url=page_url, filter_url=filter_url, years=coverage, components=components,
            total_files=sum(r['files'] for r in coverage), total_qp=sum(r['qp'] for r in coverage),
            total_pages=sum(r['searchable_pages'] for r in coverage))

    @app.get('/api/search')
    def search_api():
        return jsonify(lib.search(request.args.get('q',''),request.args,request.args.get('page',1),request.args.get('size',15),request.args.get('mode')=='phrase'))

    @app.get('/coverage')
    def coverage():
        with lib.connect() as db:
            unfinished = [dict(r) for r in db.execute("SELECT * FROM documents WHERE status!='ready' ORDER BY year DESC,filename")]
            runs = [dict(r) for r in db.execute('SELECT * FROM source_runs ORDER BY id DESC LIMIT 12')]
            discovered = db.execute('SELECT count(*) FROM catalog WHERE state!=\'imported\'').fetchone()[0]
        return render_template('coverage.html', years=lib.coverage(),unfinished=unfinished,runs=runs,discovered=discovered)

    @app.get('/api/coverage')
    def coverage_api():
        return jsonify(lib.coverage())

    @app.get('/import')
    def import_page():
        return render_template('import.html')

    @app.post('/api/import')
    def import_api():
        files = request.files.getlist('files')
        if not files:
            raise ValueError('请选择 PDF 文件')
        if len(files) > 100:
            raise ValueError('单次最多上传 100 个文件')
        result = []
        for f in files:
            path = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.pdf', dir=lib.home / 'cache', delete=False) as tmp:
                    path = Path(tmp.name)
                    f.save(tmp)
                result.append(lib.import_pdf(path, filename=f.filename, source='local-upload',url=request.form.get('source_url','')))
            except Exception as exc:
                result.append({'filename':f.filename,'error':str(exc)})
            finally:
                if path:
                    path.unlink(missing_ok=True)
        return jsonify(items=result)

    @app.get('/document/<int:doc_id>')
    def document(doc_id):
        doc = lib.document(doc_id)
        with lib.connect() as db:
            sources = [dict(r) for r in db.execute('SELECT * FROM sources WHERE doc_id=?',(doc_id,))]
            units = [dict(r) for r in db.execute('SELECT * FROM units WHERE doc_id=? AND label IS NOT NULL ORDER BY page_start,id',(doc_id,))]
            correction = db.execute('SELECT spans_json FROM corrections WHERE doc_id=?',(doc_id,)).fetchone()
            pages = [dict(r) for r in db.execute('SELECT page,status FROM pages WHERE doc_id=? ORDER BY page',(doc_id,))]
        return render_template('document.html',doc=doc,sources=sources,units=units,pages=pages,
            related=lib.related(doc),correction=json.dumps(json.loads(correction[0]),indent=2,ensure_ascii=False) if correction else '[]')

    @app.post('/api/document/<int:doc_id>/corrections')
    def corrections(doc_id):
        payload = request.get_json(silent=True)
        if payload is None:
            raise ValueError('JSON 格式错误')
        lib.correct(doc_id,payload)
        return jsonify(ok=True)

    @app.post('/api/document/<int:doc_id>/reset-corrections')
    def reset(doc_id):
        lib.document(doc_id)
        with lib.connect() as db:
            db.execute('DELETE FROM corrections WHERE doc_id=?',(doc_id,))
        lib.index_document(doc_id)
        return jsonify(ok=True)

    @app.get('/api/document/<int:doc_id>/lines')
    def lines(doc_id):
        lib.document(doc_id)
        with lib.connect() as db:
            rows = db.execute('SELECT page,status,lines_json FROM pages WHERE doc_id=? ORDER BY page',(doc_id,)).fetchall()
        return jsonify([{'page':r['page'],'status':r['status'],'lines':[{'line':n,'text':l['text']} for n,l in enumerate(json.loads(r['lines_json']),1)]} for r in rows])

    @app.get('/pdf/<int:doc_id>')
    def pdf(doc_id):
        doc = lib.document(doc_id)
        return send_file(lib.pdf_path(doc), mimetype='application/pdf',download_name=doc['filename'],conditional=True)

    @app.get('/viewer/<int:doc_id>')
    def viewer(doc_id):
        doc = lib.document(doc_id)
        page = int(request.args.get('page',1))
        if not 1 <= page <= doc['page_count']:
            abort(404)
        ms = next((r for r in lib.related(doc) if r['kind']=='ms'),None) if doc['kind']=='qp' else None
        with lib.connect() as db:
            questions = [dict(r) for r in db.execute('SELECT label,page_start,page_end,confidence FROM units WHERE doc_id=? AND label IS NOT NULL ORDER BY page_start,id',(doc_id,))]
        config = dict(doc=doc,ms=ms,page=page,explicit_page='page' in request.args,
                      question=request.args.get('question',''),focus=request.args.get('focus','question'),
                      query=request.args.get('q',''),questions=questions)
        return render_template('viewer.html',doc=doc,page=page,related=lib.related(doc),config=config)

    @app.get('/api/reader/<int:doc_id>/page/<int:number>')
    def page_layout(doc_id,number):
        return jsonify(reader.layout(doc_id,number))

    @app.post('/api/reader/<int:doc_id>/page/<int:number>/coordinates')
    def page_coordinates(doc_id,number):
        return jsonify(reader.layout(doc_id,number,repair=True))

    @app.get('/api/reader/<int:doc_id>/answer')
    def answer_location(doc_id):
        return jsonify(reader.resolve(doc_id,request.args.get('question','')))

    @app.post('/api/reader/<int:doc_id>/answer')
    def save_answer(doc_id):
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict) or not all(k in payload for k in ('ms_doc_id','label','ranges')):
            raise ValueError('缺少题号、评分标准或答案范围')
        return jsonify(reader.save_link(doc_id,payload))

    @app.post('/api/reader/<int:doc_id>/answer/reset')
    def reset_answer(doc_id):
        from biology.reader import label
        lib.document(doc_id)
        k=label((request.get_json(silent=True) or {}).get('label',''))
        with lib.connect() as db:
            db.execute('DELETE FROM answer_links WHERE qp_doc_id=? AND label=?',(doc_id,k))
        return jsonify(reader.resolve(doc_id,k))

    @app.get('/api/reader/<int:doc_id>/question')
    def question_text(doc_id):
        lib.document(doc_id)
        return jsonify(reader.question(doc_id,request.args.get('question','')))

    @app.get('/api/reader/<int:doc_id>/directory')
    def answer_directory(doc_id):
        return jsonify(reader.directory(doc_id))

    @app.get('/api/reader/<int:doc_id>/find')
    def find_in_doc(doc_id):
        return jsonify(items=reader.find(doc_id,request.args.get('q','')))

    @app.get('/page/<int:doc_id>/<int:number>.png')
    def page_image(doc_id,number):
        doc = lib.document(doc_id)
        with fitz.open(lib.pdf_path(doc)) as pdf:
            if not 1 <= number <= len(pdf):
                abort(404)
            data = pdf[number-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).tobytes('png')
        return send_file(io.BytesIO(data),mimetype='image/png',max_age=3600)

    @app.get('/health')
    def health():
        with lib.connect() as db:
            count = db.execute('SELECT count(*) FROM documents').fetchone()[0]
        return jsonify(status='ok',documents=count)

    return app


if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get('BIOLOGY_PORT','9700'))
    print(f'本地题库已启动：http://127.0.0.1:{port}',flush=True)
    serve(create_app(),host='127.0.0.1',port=port,threads=4)
