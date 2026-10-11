"""Conservative source adapters. Live schemas must pass validation before import."""
import hashlib
import json
import logging
import re
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from biology.library import metadata

USER_AGENT = 'Biology9700PersonalLibrary/1.0 (personal educational archive; rate limited)'
FRAFT_DOWNLOAD_BASE = 'https://cie.fraft.cn/obj/Common/Fetch/redir/'


def fraft_download_url(filename):
    """Current route observed in the user's successful browser PDF response."""
    metadata(filename)
    if '/' in filename or '\\' in filename:
        raise ValueError('Fraft 文件名不能包含目录')
    return FRAFT_DOWNLOAD_BASE + quote(filename)


class SourceBlocked(RuntimeError):
    pass


class Client:
    def __init__(self, home, delay=2.0, refresh=False):
        self.cache = Path(home) / 'cache'
        self.cache.mkdir(parents=True,exist_ok=True)
        self.delay = max(1.0,float(delay))
        self.refresh = refresh
        self.session = requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT
        self.robots = {}
        self.last = 0

    def _request(self, method, url, **kwargs):
        if self.delay > 60:
            raise SourceBlocked(f'来源要求至少间隔 {self.delay} 秒；停止本次任务，稍后再执行')
        for attempt in range(3):
            time.sleep(max(0,self.last+self.delay-time.monotonic()))
            self.last = time.monotonic()
            try:
                r = self.session.request(method,url,timeout=(15,90),allow_redirects=False,**kwargs)
                logging.info('%s %s -> %s',method,url,r.status_code)
                if r.status_code in (401,403):
                    r.close()
                    raise SourceBlocked(f'来源拒绝访问 HTTP {r.status_code}：{url}；不重试或绕过')
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    retry = r.headers.get('Retry-After','')
                    retry_seconds = int(retry) if retry.isdigit() else 0
                    if retry and not retry.isdigit():
                        try:
                            retry_seconds = max(0,parsedate_to_datetime(retry).timestamp()-time.time())
                        except (ValueError,TypeError,OverflowError):
                            pass
                    wait = max(2**(attempt+1),retry_seconds)
                    if wait > 60:
                        r.close()
                        raise SourceBlocked(f'来源 Retry-After 要求等待约 {int(wait)} 秒；本次停止，不提前重试')
                    if attempt == 2:
                        r.raise_for_status()
                    r.close()
                    time.sleep(wait)
                    continue
                return r
            except requests.RequestException as exc:
                if '403' in str(exc) or 'Forbidden' in str(exc):
                    raise SourceBlocked(f'网络策略或来源拒绝连接：{url}：{exc}') from exc
                if attempt == 2:
                    raise
                time.sleep(2**(attempt+1))
        raise RuntimeError('请求失败')

    def allowed(self, url):
        p=urlparse(url)
        if p.scheme!='https' or not p.netloc or p.username or p.password:
            raise SourceBlocked('仅接受不含凭证的公开 HTTPS 链接')
        origin=f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            r=self._request('GET',origin+'/robots.txt')
            if r.status_code == 404:
                lines=[]
            elif r.status_code == 200 and ('text' in r.headers.get('Content-Type','') or not r.content.strip()):
                lines=r.text.splitlines()
            else:
                raise SourceBlocked(f'无法确认 robots.txt（HTTP {r.status_code}），停止该来源自动获取')
            rp=RobotFileParser()
            rp.parse(lines)
            self.robots[origin]=rp
            (self.cache / (hashlib.sha256(origin.encode()).hexdigest()+'.robots.txt')).write_text('\n'.join(lines),encoding='utf-8')
        rp=self.robots[origin]
        if not rp.can_fetch(USER_AGENT,url):
            raise SourceBlocked(f'robots.txt 不允许访问：{url}')
        self.delay=max(self.delay,rp.crawl_delay(USER_AGENT) or rp.crawl_delay('*') or 0)

    def request(self,method,url,**kwargs):
        for _ in range(6):
            self.allowed(url)
            r=self._request(method,url,**kwargs)
            if r.status_code in (301,302,303,307,308):
                next_url=urljoin(url,r.headers['Location'])
                r.close()
                if r.status_code in (301,302,303):
                    method='GET'
                    kwargs.pop('data',None)
                url=next_url
                continue
            r.raise_for_status()
            return r
        raise SourceBlocked('重定向过多')

    def text(self,url,form=None):
        key=hashlib.sha256((url+json.dumps(form,sort_keys=True)).encode()).hexdigest()
        cached=self.cache/(key+'.response')
        if cached.exists() and not self.refresh:
            return cached.read_text(encoding='utf-8')
        r=self.request('POST' if form else 'GET',url,**({'data':form} if form else {}))
        text=r.text
        # Never cache a challenge page as a successful source response.
        if any(s in text.lower() for s in ('cf-chl-', 'verify you are human', 'captcha')):
            raise SourceBlocked('检测到访问验证页面，停止自动获取')
        cached.write_text(text,encoding='utf-8')
        return text

    def json(self,url,form=None):
        try:
            return json.loads(self.text(url,form))
        except json.JSONDecodeError as exc:
            raise SourceBlocked('接口未返回 JSON；可能已变更或要求登录，停止该来源') from exc

    def pdf(self,url):
        key=hashlib.sha256(url.encode()).hexdigest()
        final=self.cache/(key+'.pdf')
        partial=self.cache/(key+'.part')
        validator=self.cache/(key+'.validator.json')
        if final.exists():
            return final
        for attempt in range(3):
            offset=partial.stat().st_size if partial.exists() else 0
            headers={}
            saved=json.loads(validator.read_text()) if validator.exists() else {}
            # Resume only with a server validator; otherwise restart safely.
            if offset and saved.get('validator'):
                headers={'Range':f'bytes={offset}-','If-Range':saved['validator']}
            else:
                offset=0
            try:
                r=self.request('GET',url,headers=headers,stream=True)
                if r.status_code==206:
                    cr=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',r.headers.get('Content-Range',''))
                    if not cr or int(cr[1])!=offset:
                        r.close()
                        partial.unlink(missing_ok=True)
                        validator.unlink(missing_ok=True)
                        if attempt==2:
                            raise ValueError('服务器 Range 响应不完整，无法安全续传')
                        continue
                else:
                    offset=0
                val=r.headers.get('ETag') or r.headers.get('Last-Modified')
                validator.write_text(json.dumps({'validator':val}),encoding='utf-8')
                count=0
                with partial.open('ab' if offset else 'wb') as f:
                    for chunk in r.iter_content(128*1024):
                        count+=len(chunk)
                        if count+offset>128*1024*1024:
                            raise ValueError('单个 PDF 超过 128 MB 限制')
                        f.write(chunk)
                if r.headers.get('Content-Length') and count!=int(r.headers['Content-Length']):
                    raise ValueError('PDF 下载未完成')
                r.close()
                with partial.open('rb') as f:
                    if not f.read(1024).lstrip().startswith(b'%PDF-'):
                        raise ValueError('下载结果不是 PDF，未导入')
                import fitz
                with fitz.open(partial) as document:
                    if document.needs_pass or len(document)==0:
                        raise ValueError('PDF 加密或为空')
                partial.replace(final)
                return final
            except requests.RequestException as exc:
                if getattr(exc, 'response', None) is not None and exc.response.status_code == 416:
                    partial.unlink(missing_ok=True)
                    validator.unlink(missing_ok=True)
                    if attempt < 2:
                        continue
                if attempt==2:
                    raise
                time.sleep(2**(attempt+1))
        raise RuntimeError('PDF 下载失败')


def record_run(lib,source,state,details):
    with lib.connect() as db:
        db.execute('INSERT INTO source_runs(source,state,details) VALUES(?,?,?)',(source,state,details))
    logging.info('%s %s %s',source,state,details)


def add_catalog(lib,source,original_id,name,url,raw):
    meta=metadata(name)
    with lib.connect() as db:
        db.execute('''INSERT INTO catalog(source,original_id,filename,url,metadata_json) VALUES(?,?,?,?,?)
          ON CONFLICT(source,original_id) DO UPDATE SET url=excluded.url,metadata_json=excluded.metadata_json,updated_at=CURRENT_TIMESTAMP''',
          (source,str(original_id),meta['filename'],url,json.dumps(raw,ensure_ascii=False)))
    return meta['filename']


def discover_papersc(lib,client,years):
    count=0
    for year in years:
        for season in 'msw':
            query=f'9700 {season}{year%100:02}'
            url='https://paper.sc/search/?'+urlencode({'query':query,'as':'json'})
            data=client.json(url)
            if not isinstance(data,dict) or data.get('response') not in ('pp','overflow'):
                raise SourceBlocked('PaperSC 响应结构与已研究源码不符')
            if data['response']=='overflow':
                raw=client.text('https://paper.sc/search/?'+urlencode({'query':query,'as':'raw','wlinks':'1'}))
                rows=[]
                for line in raw.strip().splitlines():
                    name,sep,link=line.partition('\t')
                    if not sep or not re.fullmatch(r'https://paper.sc/doc/[a-f0-9]+/',link):
                        raise SourceBlocked('PaperSC raw 列表格式异常；不把不完整结果当作完整目录')
                    rows.append({'filename':metadata(name+'.pdf')['filename'],'_id':link.rstrip('/').split('/')[-1]})
            else:
                if not isinstance(data.get('list'),list):
                    raise SourceBlocked('PaperSC list 不是数组')
                rows=data['list']
            for row in rows:
                if 'filename' in row:
                    name=row['filename']
                else:
                    if str(row.get('subject'))!='9700' or row.get('time')!=f'{season}{year%100:02}':
                        raise SourceBlocked('PaperSC 返回了不匹配的科目或考季')
                    if row.get('fileType')!='pdf' or row.get('type') not in ('qp','ms','er','gt','ci','ir','in'):
                        continue
                    pv=f"{row['paper']}{row['variant']}" if row.get('paper') else ''
                    name=f"9700_{row['time']}_{row['type']}"+(f'_{pv}' if pv else '')+'.pdf'
                oid=str(row['_id'])
                if not re.fullmatch('[a-f0-9]{24}',oid):
                    raise SourceBlocked('PaperSC 文档标识无效')
                add_catalog(lib,'papersc',oid,name,f'https://paper.sc/doc/{oid}/',row)
                count+=1
    return count


def discover_fraft(lib,client,years):
    # Research lead: github.com/iewnfod/get_paper_rs. Not asserted to be a stable live API.
    count=0
    for year in years:
        for season,letter in [('Mar','m'),('Jun','s'),('Nov','w')]:
            form={'subject':'9700','year':str(year),'season':season}
            data=client.json('https://cie.fraft.cn/obj/Fetch/renum',form)
            if not isinstance(data,dict) or not isinstance(data.get('rows'),list) or 'total' not in data:
                raise SourceBlocked('Fraft 响应与研究线索不符，需重新核查接口')
            if int(data['total'])!=len(data['rows']):
                raise SourceBlocked('Fraft 返回分页或截断列表；未验证分页协议，停止并保留错误')
            for row in data['rows']:
                name=row.get('file','')
                try:
                    meta=metadata(name)
                except ValueError:
                    continue
                if '/' in name or meta['year']!=year or meta['season']!=letter:
                    raise SourceBlocked('Fraft 文件名或考季异常')
                add_catalog(lib,'fraft',name,name,fraft_download_url(name),row)
                count+=1
    return count


def discover_html(lib,client,url,source='html'):
    soup=BeautifulSoup(client.text(url),'html.parser')
    count=0
    for a in soup.select('a[href]'):
        link=urljoin(url,a['href'])
        text=a.get_text(' ',strip=True)+' '+link
        match=re.search(r'9700_[mswy]\d{2}_(?:qp|ms|er|gt|ci|ir|in)(?:_[1-5]\d)?\.pdf',text,re.I)
        if match:
            try:
                add_catalog(lib,source,link,match[0],link,{'listing_url':url,'text':a.get_text(' ',strip=True)})
                count+=1
            except ValueError:
                continue
    if not count:
        raise SourceBlocked('未发现标准文件名的直接 PDF 链接；不猜测隐藏 API 或构造文件')
    return count


def download_catalog(lib,client,source,limit=None):
    with lib.connect() as db:
        rows=db.execute("SELECT * FROM catalog WHERE source=? AND state!='imported' ORDER BY filename LIMIT ?",(source,limit if limit is not None else -1)).fetchall()
    counts={'imported':0,'failed':0}
    for row in rows:
        try:
            file=client.pdf(row['url'])
            result=lib.import_pdf(file,filename=row['filename'],source=source,url=row['url'],original_id=row['original_id'])
            with lib.connect() as db:
                db.execute("UPDATE catalog SET state='imported',error='',updated_at=CURRENT_TIMESTAMP WHERE source=? AND original_id=?",(source,row['original_id']))
            counts['imported']+=1
            logging.info('IMPORTED %s %s',row['filename'],result)
        except Exception as exc:
            counts['failed']+=1
            with lib.connect() as db:
                db.execute("UPDATE catalog SET state='failed',error=?,updated_at=CURRENT_TIMESTAMP WHERE source=? AND original_id=?",(str(exc),source,row['original_id']))
            logging.exception('FAILED %s',row['filename'])
            if isinstance(exc,SourceBlocked):
                raise
    return counts
