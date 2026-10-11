# 来源研究与验证边界

研究日期：2026-10-10。网页工具的抓取可能使用其缓存，因此“网页可见”与“当前 API 实时返回”分开记录。

## PaperSC

- [官网](https://paper.sc/)可以通过网页检索工具读取。首页 API 链接直接指向 [micromaomao/schsrch/index.js](https://github.com/micromaomao/schsrch/blob/master/index.js)，已实际点击核实。
- 仓库公开可读，已克隆。研究版本 `2875778d18d558452ab9cb6a1da476546a5ecbb8`，提交时间 2023-12-30，提交消息 Remove dead badges。仓库更新时间不能用来推断数据库更新时间。
- [9700 科目列表](https://paper.sc/search/?as=page&query=9700) 的可见考季到 **s23（2023 May/June）**：m23=10 文件、s23=34 文件，未列 w23 或 2024–2026。不是以搜索框里出现“2025”等文字判断收录。
- 2016 起可见目录计数：m16 11 / s16 41 / w16 41 / y16 9；m17 13 / s17 41 / w17 41；m18 14 / s18 41 / w18 41；m19 13 / s19 40 / w19 34；2020–2022 各年 m 10 / s 34 / w 34。计数包括多种文件，不等于试卷套数。
- [s23 列表](https://paper.sc/search/?as=page&query=9700+s23)实测显示 QP/MS 配对：11、12、13、21、22、23、31、32、33、34、35、41、42、43、51、52、53，共 34 文件。
- 已通过网页工具打开真实 [9700 s23 QP41](https://paper.sc/doc/67f9af77778c77000cf6f571/)，识别为 application/pdf，24 页，封面确为 Biology 9700/41 May/June 2023。这证明该文档链接可供网页工具读取；没有取得可保存到执行器的 PDF 字节，**没有计入本地题库**。

### 源码协议（已经读过，不宣称全部在线验证通过）

对应源码：index.js、lib/parseQuery.js、lib/doSearch.js、lib/dbModel.js、lib/recognizer.js。

| 能力 | 源码定义 | 本次实测状态 |
|---|---|---|
| 结构化查询 | `/search/?query=9700+s23+qp+12&as=json`；也识别 `9700_s23_qp_12.pdf`、`9700/12/M/J/23`、`9700 paper 1` | JSON 请求未能在线验证 |
| JSON 试卷列表 | `response:'pp'`, `list`, `typeFilter`；文档字段 `_id,subject,time,paper,variant,type,fileType,numPages` | 源码确认；网页版列表实测可见 |
| 过多结果 | 非 raw 查询 limit=71；`overflow`；单科目总览含 `times:[{time,count}],metaDocs` | 网页科目总览可见；脚本防止当作空结果 |
| raw 完整列表 | `as=raw&wlinks=1`；每行 `9700_s23_12_qp`、TAB、文档 URL；`wlinks=only` 只输出 URL | 源码确认；未验证在线返回。raw 不支持全文检索 |
| PDF | `/doc/:id` 默认 blob；文件名是 `setToString + '_' + type`；指定 page 与 blob 不兼容 | 上述 QP41 链接已通过网页工具读取；执行器下载受限 |
| 题目目录 | `/doc/:id?as=dir`；`/dirs/batch/?docid=...` 可关联文件 | 源码确认；未验证在线响应。目录有 questions/mcqMs/er 等不同类型 |
| 页面提取 | `/doc/:id?as=sspdf&page=0`；源码页码从 0 开始 | 未在线验证；本地统一使用从 1 开始的 PDF 物理页码 |
| 全文检索 | 非结构化 query 转 Elasticsearch，`9700 mitochondria` 可限定科目；响应 `text`、`list:[{doc,index,related}]`，index 含 content/page | 源码确认；线上文字查询尝试失败；日常搜索完全改用本地 SQLite FTS5 |

执行器请求 `https://paper.sc/robots.txt` 返回代理 `Tunnel connection failed: 403 Forbidden`。当前云环境网络策略只允许 GitHub、包管理站点等白名单，未允许 paper.sc。网页工具对 JSON、raw、部分搜索请求报告 not accessible。未修改代理、未绕过规则。`manage.py probe --source papersc` 已实际运行，数据库 source_runs 和 data/logs/import.log 保留该错误。连接恢复后脚本会先检查 robots、查询结构和 PDF，再导入。

### 三种许可必须区分

1. **代码**：[schsrch LICENSE](https://github.com/micromaomao/schsrch/blob/master/LICENSE) 为 MIT。本项目没有复制其实现，只研究其协议。
2. **线上 API**：首页公开提供 API 源码链接，没有在已读页面找到服务保证、固定版本或独立 SLA。源码 `/robots.txt` 返回空文本，但不能据此认定线上 robots 仍相同。脚本每次联网检查当前 robots、低速访问；401/403/验证页停止，429 尊重重试时间，不登录或绕过限制。
3. **试卷内容**：[PaperSC Disclaimer](https://paper.sc/disclaim/)声明版权归 UCLES、教育用途。MIT 不授予试卷内容版权。公开托管也不是再分发授权。项目只面向用户本地个人学习，不提供公开发布或商业化功能。

## Fraft（优先检查的 2024–2026 来源）

- 首先检查了 [用户提供的移动版](https://cie.fraft.cn/?show=mobile) 和根目录；网页工具两者均返回 502 Bad Gateway。
- 执行器请求 robots.txt 被同一环境网络白名单以代理 403 阻止。不能据此断言网站对所有用户不可用。
- 找到公开的第三方 [iewnfod/get_paper_rs](https://github.com/iewnfod/get_paper_rs)，已克隆并读取 `src/ui/data.rs` 和 `src/ui/network.rs`。它明确说明来源为 cie.fraft.cn。
- 其中的研究线索是：GET `/obj/Combo/subject`；POST `/obj/Fetch/renum`，form 字段 `subject=9700, year=2026, season=Mar/Jun/Nov`；预期响应 `total`、`rows`、行内 `file`；下载 `/obj/Fetch/redir/{file}`。
- 已据此实现 **防御式、尚未在线验证的适配器**。实时响应不匹配就停止；如果 total 与 rows 长度不同，视为可能分页/截断，不猜测分页接口。不照搬该第三方程序的无限重试。
- **实际年份、Paper/Variant、2026 QP/MS 完整性仍无法确认；本地导入 0 个 Fraft 文件。** 程序不会把这些线索转成已收录记录。`manage.py probe --source fraft` 实测错误已保存。
- 用户已明确允许 2024–2026 稍后提供本地 PDF；现在可以在网站多选上传，或命令行递归导入，并填写 Fraft 下载页面链接保留来源。

## 其他公开来源

### 已实际获取的历史资料

[vascodegraaff/CIE-A-level-past-papers](https://github.com/vascodegraaff/CIE-A-level-past-papers)，研究提交 `7696de0d671103b675d57a29d6a864050ae34b2f`。该公开仓库介绍为共享历年试卷。使用正常 git clone / sparse-checkout 读取 `Biology - 9700/2016` 至 `2019`，没有抓取其他科目或访问限制后的隐藏地址。

先导入少量 QP/MS，通过真实关键词与物理页码验收，再导入范围内标准命名文件。所有导入文件保留提交号、仓库文件 URL、原始文件名与 SHA-256。三个同名异内容 PDF 被隔离在 data/quarantine，没有覆盖旧版本。详细数量与索引状态以 COVERAGE.md 为准。这个仓库不是 Cambridge 官方授权声明；试卷版权仍归原权利人。

### 2024–2026 的补充线索（没有冒充已收录）

- [Cambridge 官方 9700 历年资料页](https://www.cambridgeinternational.org/programmes-and-qualifications/cambridge-international-as-and-a-level-biology-9700/past-papers/)可读，说明公开部分为选集，学校完整资源需要 School Support Hub。未访问登录后的资料。当前网页提取未得到可批量获取的 PDF 列表。
- [LumiExams 2026 March 9700 目录](https://lumiexams.com/a-level/biology-9700/2026/mar/)可读，列出 12、22、33、42、52 的 QP/MS、CI、ER、GT；链接指向 PapaCambridge。目录文本中还有不一致的泛化描述，因此仅将实际链接作为后续线索，不采信“完整”宣传。
- 网页检索还找到了 [2024 March MS42](https://igunioneg.com/past-papers/cambridge/?download=force&id=2&view=%2FAS+And+A+Level%2FBiology+9700%2F2024+March%2F9700_m24_ms_42.pdf) 和 [2025 March MS42](https://pastpapers.papacambridge.com/directories/CAIE/CAIE-pastpapers/upload/9700_m25_ms_42.pdf)的索引。未取得执行器可保存的原 PDF，未导入。
- 通用 `manage.py from-page URL` 能读取明确公开链接；不会自动递归猜测全部年份或猜造 2026 文件。所有下载仍须通过当前来源的 robots 和访问检查。

## 可重复验证

```bash
python manage.py probe --source papersc
python manage.py probe --source fraft
python manage.py sync --source papersc --years 2023 --limit 2 --refresh
python manage.py sync --source fraft --years 2024:2026 --discover-only --refresh
```

探测失败会退出非零并记录 blocked；不会把请求失败当成 0 文件或宣布接口可用。`probe` 成功才说明该次样本协议可用，不意味着永久稳定或全年齐全。
