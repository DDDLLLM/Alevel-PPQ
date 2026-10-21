# 9700 Biology 学生在线题库

学生页面由 Sites 发布，`student-data/` 由 GitHub Pages 提供公开 PDF、目录和分年文字索引。学生无需登录；公开文件可被任何人访问。试卷版权归 Cambridge / UCLES 所有。

## 更新资料

先在原本地题库中完成导入、OCR 和核对，然后从仓库根目录运行：

```sh
python student-site/scripts/export_library.py --data /path/to/local/data --output student-data
```

在线题库固定为 **2022–2026 年**，导出器自动排除 2020、2021 年。当前为 468 个文件、195 份试卷。旧 PDF 可作为归档保留，网站不再检索它们。

导出器使用 SQLite 一致快照，不修改老师数据库；校验全部原 PDF 的 SHA-256，再按标准试卷名复制，输出 `manifest.json`、`catalog.json`、分年索引和保守识别的 MS 题号目录。不导出缓存、备份、下载记录或本地路径。

检查后将 `student-data/` 的变化推送到 main。GitHub Actions 自动更新公开文件。GitHub Pages 的 Source 应设为 GitHub Actions。

## 前端

`student-site/dist/` 是可直接托管的静态页面。`config.js` 指向 GitHub Pages 数据地址。界面支持筛选、关键词/连续原文搜索、标准文件名搜索、PDF.js 双栏原 PDF 阅读、题号目录跳转、当前卷/页码分享。老师的导入与修正仍在本机完成。

PDF.js 5.4.296 来自官方 npm 包，许可证见 `dist/vendor/PDFJS-LICENSE`。代码不依赖外部字体或 CDN。

搜索默认查找同一 PDF 页中的全部英文关键词，兼容常见单复数变化；连续原文模式匹配相邻单词。搜索在浏览器 Worker 中进行，索引按年份和资料类型拆分，以 gzip 形式按需加载。浏览器下载后只分词一次，后续查询通过倒排索引定位候选页面，并缓存内容。默认试题搜索的全部压缩索引约 1.39 MB。搜索结果按 PDF 页显示，不声称精确切分全部题目。MS 自动定位应以原卷为准。没有可靠目录时保留手动翻页。
