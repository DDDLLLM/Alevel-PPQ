# 阅读与答案定位升级（2026-10-13）

此升级使用你现有的 `data/`，无需运行 sync、install-papers 或重新 OCR 全库。年份多少、收录多少，以你自己的“收录情况”为准。开发环境的 330 文件不是你电脑题库的数量。

## Windows 更新

1. 在运行网站的终端按 `Ctrl+C`，关闭旧网站。确认当前目录是原项目文件夹（包含 `manage.py`、`requirements.txt`、`data`）。
2. 先备份。在原项目的 CMD 中执行以下命令；目标目录必须尚不存在，重复备份时换一个名称：

   ```bat
   .venv\Scripts\python.exe manage.py backup "..\9700-backup-before-reader"
   ```

   也可以停服后，把整个原项目文件夹复制到另一处。若用 `BIOLOGY_DATA` 指定过目录，备份与新启动都要使用同一个数据目录。
3. 在 GitHub 仓库点 **Code → Download ZIP**，解压到临时文件夹。把里面的 `app.py`、`manage.py`、`requirements.txt`、`start.bat`、`start.sh`，以及整个 `biology`、`templates`、`static`、`scripts`、`docs` 文件夹复制到**原项目文件夹**，选择合并并替换同名代码文件。可以同时复制 README 与 tests。**保留原有 `data`、`.venv` 和自己的配置，不拿新文件夹覆盖或删除它们。**
4. 双击原项目内的 `start.bat`；浏览器打开 http://127.0.0.1:9700，按 `Ctrl+F5` 刷新缓存。
5. 在“收录情况”核对原数量，再搜索一段熟悉的题目，点“查看对应答案”。无需重建搜索索引。

## Mac 更新

1. 在旧网站终端按 `Control+C`。终端进入原项目文件夹，先备份：

   ```bash
   .venv/bin/python manage.py backup ../9700-backup-before-reader
   ```

2. 下载并解压同一个 ZIP。**Finder 替换整个文件夹可能删除旧内容**，建议在原项目终端复制代码。假设新 ZIP 解压在 `~/Downloads/Alevel-PPQ-main`（按真实位置调整）：

   ```bash
   cp ~/Downloads/Alevel-PPQ-main/{app.py,manage.py,requirements.txt,start.sh,start.bat} .
   cp -R ~/Downloads/Alevel-PPQ-main/{biology,templates,static,scripts,docs} .
   bash start.sh
   ```

3. 打开 http://127.0.0.1:9700 并按 `⌘⇧R` 强制刷新。原 `data/` 与 `.venv` 留在原位置。

## 如何使用

- 首页直接点年份、`m22/s22/w22`、组件 `21/22/23` 和文件类型。`m` = March（2–3月）、`s` = Summer（5–6月）、`w` = Winter（10–11月）。数量是实际导入的文件，包含 QP/MS/ER 等，不是完整套数或“已发布总数”。缺少考季显示“未收录”。
- 输入英文关键词后点击搜索。筛选按钮立即更新结果并保留已提交的关键词。搜索结果直接打开题目或对应答案。
- 阅读器左右分别是 QP/MS。各自翻页、放大、滚动；切换“只看题目/只看答案”不会丢失另一边的位置。物理 PDF 页码从 1 开始。
- 题号框支持 `4`、`4(a)`、`4(a)(iii)`。可展开 MS 题号目录点击子题。QP 子题仅在既有主问题目录和版面缩进序列通过校验时自动识别；否则提示核对原卷，保留阅读页。
- **已人工确认**：人工保存的范围或旧人工页码。旧记录只确认了 MS 页码时，继续尊重该页码，但不会因此启用“复制整题答案”。
- **自动定位**：识别到原生 MS 题号表格，或完整的 1–40 选择题答案表。高亮实际答案段落；跨页内容提供多个跳转按钮。自动结果仍需核对原卷。
- **尚未定位**：只知道关联的 MS，不能声称找到了具体答案。可在右侧卷内搜索、直接翻页，或展开“人工修正答案范围”。输入题号、开始/结束 PDF 页码与位置百分比；百分比从页面上缘向下计算。填完核对后保存。表格的多栏答案可设置左右边界，避免复制其他题。
- 拖选页面文字，按 `Ctrl+C` / `⌘C` 即可复制。按钮复制的是已确定范围的纯文字，表格及图表始终保留在原卷视觉页面中。OCR 来源有明确提示。
- “复制题目文字/复制答案文字”仅在确认了相应文字范围后可用。不确定时可以展开“本页文字”按需选择，也可到文件详情使用原有题目目录修正。

## 已有 OCR 缺少坐标怎么办

搜索用的 OCR 纯文字不一定带页面坐标。阅读器若提示“缺少坐标”，点 **补齐本页文字坐标**，只处理这一页。原 OCR、搜索索引和人工记录不变；已有坐标缓存不会重复处理。运行环境仍需原来 OCR 使用的 Tesseract + eng 语言包。

如果希望提前处理 2022–2026 的坐标，可选择执行（不是必需）：

Windows CMD：

```bat
.venv\Scripts\python.exe manage.py prepare-reader --years 2022:2026 --ocr
```

Mac：

```bash
.venv/bin/python manage.py prepare-reader --years 2022:2026 --ocr
```

不加 `--ocr` 只提取原生坐标、缓存 MS 目录并统计缺少坐标的页面。可加 `--id 文件ID` 只检查一个文件。中断后重跑会利用已保存的缓存。若缺 Tesseract，页面和日志会明确提示失败，已有 OCR 可继续搜索。

该命令只补充**阅读坐标**，不会把原本未索引的页面假装为“已全文索引”。若有真正待索引文件，继续使用原来的 `reindex --ocr --pending-only`，然后按需补齐坐标。

## 数据、迁移与恢复

- 原始文件：`data/pdfs/<SHA256>.pdf`，从不改写。
- 原数据库：`data/library.sqlite3`，继续保存 `documents/pages/units/search_fts/corrections`。
- 新增表：`page_layouts`（文字坐标缓存）、`answer_directories`（自动 MS 目录）、`answer_links`（人工 QP/MS 答案范围）。人工答案关系使用文件 ID + 题号，不依赖重建时变化的搜索单元 ID。
- 首次升级自动把 SQLite 从版本 1 迁移为 2；新增表，不清空、重新导入或重建旧表。迁移前通过 SQLite backup API 保存 `data/backups/before-reader-v2-时间.sqlite3`。重复启动不重复迁移、不降级版本。自动迁移备份仅包含数据库；完整备份还需 PDF，因此建议先执行上面的 backup 命令。
- `python manage.py backup 目标新目录` 已能同时备份新旧数据库表及原 PDF。恢复时停服，保留现目录副本，把完整备份恢复为 `data`，或通过 `BIOLOGY_DATA` 指向备份目录。不要在网站运行中只复制 `.sqlite3` 而漏掉 WAL。
- `reindex` 保留新人工答案关系和旧人工目录。需要纠正错误关系时，在阅读器按“撤销当前题号的新答案修正”，不会删除旧目录中的人工页码。

## 已知边界

旧版无规则表格的 MS、扫描 MS、缺漏或含混的题号会回退到卷内搜索/人工修正。扫描 MS 即使补齐坐标，也不会仅凭 OCR 数字自动确认答案；可以选择复制文字并人工保存范围。坐标提取或 OCR 不是排版重建，复杂公式、旋转图中文字、上下标与表格复制为纯文本后可能需整理。原 PDF 和图表不受影响。

这是本地功能升级。没有进行学生账号、收藏、章节分类、Chapter Test 或公共部署。GitHub 提供源代码更新；你的 PDF 和数据库仍在本机。
