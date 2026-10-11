# 9700 生物个人题库

> GitHub ZIP 仅含源码。批量同步 2016–2023 各考季请运行 `bash install-2016-2023.sh --source fraft`；旧 `bash install-papers.sh` 仅安装 330 文件子集。当前 Fraft 协议已由用户浏览器证据确认，逐年完整范围仍以实际下载报告为准。

这是已经实现、导入真实文件并经过测试的本地网站。界面中文，试卷内容保留英文。仅收录 Cambridge International AS & A Level Biology（9700），年份限制为 2016–2026。

**当前交付：330 个真实 PDF，138 份 Question Paper，覆盖 2016–2019 的部分考季。2020–2026 暂未导入，2024–2026 可按你的安排稍后上传。** 具体每年数量、哪些文件尚未完成文字索引，以及来源限制见 [实际覆盖报告](docs/COVERAGE.md) 和 [来源研究](docs/RESEARCH.md)。没有使用模拟试卷充当题库。

## 在自己的电脑启动

需要 Python 3.10 或更高版本。首次安装依赖需要网络；导入后的浏览与搜索不需要联网。不需要 Node、Docker、MongoDB 或 Elasticsearch。

- **Windows**：双击 `start.bat`。如果找不到 Python，先安装 Python 3.10+（启用 Python Launcher），再运行。
- **macOS / Linux**：打开终端进入项目文件夹，运行 `bash start.sh`。
- 看到启动提示后，用浏览器打开 **http://127.0.0.1:9700**。
- 关闭终端或按 `Ctrl+C` 停止。默认只监听本机，不公开部署。

第一次启动会创建项目内 `.venv` 并安装 `requirements.txt`。以后依赖配置不变就跳过安装。端口冲突时：macOS/Linux 用 `BIOLOGY_PORT=9701 bash start.sh`；Windows 在终端先运行 `set BIOLOGY_PORT=9701`，再运行 `start.bat`。

本次已经在提供的 Linux 执行环境安装、启动并验收；这并不代表程序已经安装到你的个人电脑。源码、数据库和 PDF 都在该环境项目目录 `/workspace/Alevel-PPQ`。转移时复制整个项目，或至少复制源码及完整 `data/`；无需复制 `.venv`。

## 一键安装已有历史试卷（Mac）

GitHub ZIP 不含 PDF，但现在支持一条命令自动安装开发环境已验证的同一批 330 个文件。终端进入项目文件夹后运行：

```bash
bash install-papers.sh
```

下载约 451 MB，缓存和本地副本合计约需 1 GB 空间。保持联网并等待逐文件下载和索引，可能需要十几分钟或更久。中断后重新执行会跳过已导入文件，并继续下载。来源拒绝访问时停止，不绕过限制。完成后运行 `bash start.sh`。

只覆盖 2016–2019 的部分考季，不含 2020–2026；未安装 OCR 时文字不足页面会保留待 OCR 状态。文件从固定版本的原始公开仓库直接下载到本机，不上传 PDF 或个人数据库到本仓库。

## 补齐 2016–2023 的全部考季

330 个文件只是旧历史仓库的子集，不能满足 2016–2023 的完整范围。新的入口会优先检查 Fraft，再检查 PaperSC 和 IGCSE Union Egypt 的公开目录，按来源实际列出的文件批量下载并建立本地索引：

```bash
bash install-2016-2023.sh --source fraft
```

Fraft 当前列表与下载路径、POST 字段以及响应格式已由用户浏览器确认，样本为 2025 冬季 54 文件。`--source fraft` 只访问 Fraft；不加该选项则同时检查其他补充来源。

重新运行会跳过本地已有文件。按年、考季输出目录数、实际收录数、未下载文件和索引未完成数；详细报告在 `data/logs/2016-2023-sync.json`，请求日志在 `data/logs/range-sync.log`。遇到来源拒绝访问不会绕过，也不会宣称已经补齐。

**重要验证边界**：云开发环境对这三个域名均有网络白名单限制，因此在线下载仍未完成端到端验收，必须在能够正常访问来源的本机运行并检查报告。网页工具确认 PaperSC 的真实 2020 QP 与补充目录 2016–2023 各考季存在，但网页可见不等于本地已经导入。所有文件以成功保存、PDF 校验和索引状态为准。

## 日常使用

1. 首页选择年份、考试季、Paper、Variant、文件类型和索引状态，点击“搜索题库”；空关键词表示浏览分类。
2. 输入英文关键词（如 `mitochondria`）或题目文字。默认所有关键词都要出现；“连续原文匹配”匹配分词后的连续词序。英语词干索引支持常见单复数变化；标点不区分，不是模糊语义搜索。
3. 结果显示题号与识别来源，无法确认时显示“页面命中”。点击命中页在内置阅读器打开正确物理页；“原 PDF”同时提供标准 `#page=N` 链接。
4. 同年份、考季、Paper、Variant 的 MS 自动关联；ER/GT 按同考季关联。**MS 的具体题目页码只在人工确认后显示**，不会套用 QP 页码。
5. “收录情况”显示 2016–2026 每年的文件、QP、MS、ER、GT 和索引状态。0 表示未收录，不表示没有发布；目录记录不计入已导入数量。

真实验收样例：筛选 2016 / 2–3月 / Paper 1 / Variant 2 / 试题，搜索 `mitochondria`。命中 `9700_m16_qp_12.pdf` 第 15 题、PDF 第 6 页；正确评分标准 `9700_m16_ms_12.pdf` 在第 2 页。本例题号及 MS 页码已逐图核对并保存为人工目录。

## 补充 2024–2026 或其他本地 PDF

网站“导入 PDF”支持多选，每批最多 100 个、256 MB。逐文件处理并显示进度，错误不会阻止该批其他文件。标准命名：

```text
9700_s24_qp_12.pdf   2024 May/June，Paper 1，Variant 2，试题
9700_s24_ms_12.pdf   同卷评分标准
9700_s24_er.pdf      同考季考官报告
9700_s24_gt.pdf      同考季等级分界
9700_m26_qp_42.pdf   2026 February/March，Paper 4，Variant 2
```

`m/s/w/y` 分别是 2–3月、5–6月、10–11月、样卷。支持 qp/ms/er/gt/ci/ir/in/sp/sm，也兼容 PaperSC 的 `9700_s23_12_qp.pdf` 格式。非标准命名需先核对封面再改名；不要只为通过验证随意改年份。能提取到封面信息时会校验科目、组件、年份和考季。

命令行可以递归导入整个文件夹。先激活虚拟环境：macOS/Linux `source .venv/bin/activate`；Windows `call .venv\Scripts\activate.bat`。以下命令均在项目目录执行：

```bash
python manage.py import /path/to/my/pdfs
python manage.py import /path/to/fraft/downloads --source fraft-manual --source-url "https://cie.fraft.cn/?show=mobile"
python manage.py coverage
python scripts/report.py
```

重复导入同一文件不会新建记录，会补充来源。SHA-256 标识 PDF 内容；同名异内容或同内容异元数据会保存在 `data/quarantine/` 并报错，不静默覆盖。源仓库内已有 3 个此类冲突，日志说明具体文件。确认新版本后应先备份，再由维护者处理；网站没有危险的覆盖按钮。

## 人工修正题号、跨页题和子题

文件详情 → “人工修正题目与子题” → 展开 PDF 文字与行号 → 填写目录 JSON。所有页码和行号从 1 开始，范围包含首尾行。

```json
[
  {"label":"1(a)","page_start":2,"line_start":4,"page_end":3,"line_end":12},
  {"label":"1(b)","page_start":3,"line_start":13,"page_end":4,"line_end":8}
]
```

条目必须按原文顺序且不重叠。可只标部分题目，剩余文本自动回到页面索引。保存立即更新 FTS；重新索引保留人工目录。点击“恢复自动识别”会清除该文件的人工目录，页面会先要求确认。

如果已核对评分标准，加入 `ms_doc_id` 与 `ms_page`；MS 的本地 ID 显示在详情页。系统验证它确实属于同一套卷、页码未超界。不要填写未经核对的位置。

自动切题使用原文左侧题号位置、同一基线文本与完整连续编号校验；Paper 1 要求识别到完整 1–40 序列。序列不完整就降级为页面定位。它是保守启发式，仍应以 PDF 为准；子题默认由人工确认，未把算法结果宣传为全部正确。

## OCR 与重建索引

有文字的 PDF 直接提取；明显空白和作答留白不做 OCR。文字很少的页面会进入待处理状态，不能被算作全文索引完成。图表标签较少也可能触发保守标记。

```bash
python manage.py reindex
python manage.py reindex --id 5
python manage.py reindex --id 123 --ocr
```

普通 reindex 保留已经成功的 OCR 文字以及人工修正。`--ocr` 要求系统安装 **Tesseract + eng 语言包**。Ubuntu/Debian：`sudo apt install tesseract-ocr tesseract-ocr-eng`；macOS：`brew install tesseract`。Windows 安装 Tesseract 后，将 `TESSDATA_PREFIX` 指向含 `eng.traineddata` 的 tessdata 目录。缺少 OCR 引擎时会明确记录错误，不声称成功。

本次环境已经运行 Tesseract eng 处理少量文字不足页面。成功 OCR 会标记来源，结果可能有误字；如果识别后仍文字不足，保留未完成状态。未完成文件和页码见覆盖报告，不会藏在总数量里。重新报告：`python scripts/report.py`。

## 联网发现、导入和更新

PaperSC 与 Fraft 在本次执行环境受白名单限制，因此其在线 API 适配器**基于已读取源码，尚未完成实时协议验收**。本地题库与日常搜索不依赖这些服务。

```bash
# 先用小样本检查当前协议与下载条件
python manage.py probe --source papersc
python manage.py probe --source fraft

# 只建立已发现目录，再逐步下载
python manage.py sync --source papersc --years 2016:2023 --discover-only --refresh
python manage.py resume --source papersc --limit 4
python manage.py resume --source papersc

# Fraft 的年份与文件以实时列表和实际 PDF 为准
python manage.py sync --source fraft --years 2024:2026 --limit 4 --refresh
python manage.py resume --source fraft

# 从一个明确公开的目录页读取标准命名 PDF 链接
python manage.py from-page "https://example.org/public-directory/" --source supplement --discover-only
python manage.py resume --source supplement
```

默认每次请求至少间隔 2 秒，单进程串行；`--delay` 可调慢。当前 robots 规则、状态码、重定向目标都检查。401/403、验证码、结构变更或不明分页立即停止；对临时网络错误、5xx 和合理 Retry-After 有限重试。**不修改代理、不绕过登录或反爬。** 返回错误不会当作空目录。

元数据响应和原目录缓存在 `data/cache/`；`--refresh` 才重新获取列表。PDF 临时文件 `.part` 配合 ETag/Last-Modified 和 Content-Range 安全续传；来源不提供可靠 Range 时重新下载。导入逐文件提交事务，成功条目不重复下载；`resume` 处理剩余/失败条目。日志写入 `data/logs/`。题目目录、全文响应仅用于 probe 留存证据，不盲目信任远程切题结果。

历史仓库重现方法（只用公开 git 接口，不需要凭证）：

```bash
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/vascodegraaff/CIE-A-level-past-papers.git work/public-papers
git -C work/public-papers sparse-checkout init --cone
git -C work/public-papers sparse-checkout set "Biology - 9700/2016" "Biology - 9700/2017" "Biology - 9700/2018" "Biology - 9700/2019"
git -C work/public-papers checkout
python scripts/import_public_repository.py work/public-papers --limit 4
python scripts/import_public_repository.py work/public-papers
```

仓库内容将来可能变化；本次已导入文件的具体提交和哈希均保存在数据库及 manifest。它不是官方完整资料库。

## 数据位置与备份

```text
app.py / biology/        Flask 应用、数据库、PDF 索引、来源适配器
templates/ / static/    无外部 CDN 依赖的中文界面
manage.py               导入、发现、更新、索引、OCR、备份
scripts/                真实 PDF 验收、公开仓库导入、覆盖报告
tests/                  隔离测试及浏览器验收脚本
data/library.sqlite3    分类、全文 FTS5、来源、人工目录、远程任务状态
data/pdfs/<sha256>.pdf   原 PDF 字节，以哈希存储
data/cache/             来源响应、下载缓存、断点文件
data/quarantine/        同名异内容冲突文件
data/logs/              来源访问、导入、OCR 和重建索引日志
docs/                   中文研究、覆盖清单、测试记录
```

`BIOLOGY_DATA` 可指定其他数据目录；命令行也支持 `python manage.py --data /somewhere ...`。默认数据路径相对项目，不随当前终端工作目录改变。

安全备份（目标必须是尚不存在的新目录）：

```bash
python manage.py backup /path/to/backups/biology-2026-10-10
```

此命令使用 SQLite backup API 创建一致快照，再按该快照复制原 PDF、日志和隔离文件。恢复：停止网站，保留旧 data 副本，把备份目录作为新的 data，或设置 `BIOLOGY_DATA` 指向它，然后启动。也可停服后整体复制项目；运行中不要只复制 `.sqlite3` 而漏掉 WAL。PDF 不可仅靠数据库恢复。代码应另行保留，缓存可重建。私人 PDF/数据库已被 `.gitignore` 排除，不会意外进入源码版本库。

## 测试与实际交付状态

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/acceptance.py
```

`scripts/acceptance.py` 使用交付题库中真实 m16 QP12/MS12，在临时数据库完成新文件上传、分类、搜索、页码图像、MS关联、去重和修正持久化；不会改变用户题库。需要先有这两份真实 PDF。

浏览器测试是可选开发依赖：`npm ci`、`npx playwright install chromium`；按 `tests/browser_acceptance.cjs` 注释启动独立空测试数据目录并设置 `REAL_PDF_DIR`，然后 `npm run test:browser`。当前环境已用系统 Chromium 完成验收，包含真实上传、搜索、高亮、页码、MS、空结果与 390px 手机宽度检查。

实际机器结果见 `docs/unit-tests.txt`、`docs/acceptance.json`、`docs/browser-acceptance.json`、`docs/TEST_RESULTS.md`。测试用合成文件仅在临时目录，不进入 data。自动化通过不表示所有试卷切题或 OCR 无误；这些限制已在页面和覆盖清单明确显示。

## 版权与依赖

本项目代码在本地提供完整源文件。PaperSC 的 MIT 许可证仅适用于其代码；PDF 的 Cambridge / UCLES 版权不受该许可证覆盖。已读取来源页提供教育用途说明，未获得任何商业分发授权，也没有公开发布本项目或 PDF。

主要依赖：Flask（BSD-3-Clause）、SQLite/FTS5、PyMuPDF（AGPL-3.0 或商业许可）、requests（Apache-2.0）、Beautiful Soup（MIT）、Waitress（ZPL-2.1）。可选 Tesseract（Apache-2.0）。依赖许可证与试卷内容权利分别适用；个人本地使用无需购买商业服务。本项目没有账号、支付、远程分析或收费功能。
