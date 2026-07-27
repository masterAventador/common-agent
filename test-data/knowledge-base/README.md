# RAGFlow 召回质量人工验收语料

本目录是一套完整的虚构民生资料，用来评估 Common Agent 经 RAGFlow 完成的解析、召回、重排、
引用和跨文档问答质量。文中的城市（青川市）、社区（和风苑）、机构、文号、电话、金额、日期和
政策数值全部为测试数据，不对应任何真实行政区划或政策文件，也不是产品配置。

## 目录结构

- `corpus/`：只上传这个目录内的 12 份文档，总正文约 1.2 万中文字符。
- `expected-answers.md`：人工提问与标准答案，**禁止上传**，否则会把答案直接泄漏给检索系统。
- `../../scripts/generate-knowledge-samples.py`：重新生成 PDF 和 DOCX 两份二进制文档。

## 语料清单

| 文件 | 格式 | 文号 | 主题 |
| --- | --- | --- | --- |
| `01-garbage-sorting-guide.md` | Markdown | QC-LJ-2027-03 | 生活垃圾分类投放 |
| `02-property-service-standard.txt` | 纯文本 | HFY-WY-2027-01 | 社区物业服务规范 |
| `03-medical-insurance-guide.pdf` | PDF（6 页） | QC-YB-2027-01 | 城乡居民医保报销 |
| `04-housing-fund-guide.docx` | Word（4 页） | QC-GJJ-2027-02 | 住房公积金提取与贷款 |
| `05-dog-management-rules.md` | Markdown | QC-YQ-2027-04 | 文明养犬管理 |
| `06-ebike-management.txt` | 纯文本 | QC-DDC-2027-05 | 电动自行车管理 |
| `07-elderly-antifraud.md` | Markdown | QC-FZ-2027-06 | 老年人防诈骗 |
| `08-student-eyesight.txt` | 纯文本 | QC-SL-2027-07 | 中小学生视力保护 |
| `09-gas-electricity-safety.md` | Markdown | QC-RQ-2027-08 | 家庭用电用气安全 |
| `10-online-shopping-rights.txt` | 纯文本 | QC-XF-2027-09 | 网购与快递维权 |
| `11-public-transit-guide.md` | Markdown | QC-JT-2027-10 | 公共交通出行 |
| `12-summer-heat-flood-tips.txt` | 纯文本 | QC-YJ-2027-11 | 夏季高温与汛期 |

格式覆盖 Markdown、TXT、PDF、DOCX 四类，其中 PDF 与 DOCX 是多页排版文档，可同时验证 RAGFlow
的版面解析与分块。文号既符合政务资料惯例，也可作为逐文档召回的检索标记。

## 有意设计的检索难点

- **相同数字不同事项**：养犬登记和电动车上牌都是 30 日期限，逾期罚则却分别是 200 元和 50 元；
  公积金提取到账和物业投诉答复都是 3 个工作日，业务完全无关。
- **相近但不重合的时间段**：垃圾投放 7:00—9:00 / 18:00—20:00 与督导在岗 7:30—8:30 /
  18:30—19:30；公交晚高峰 17:00—19:00 与垃圾晚间投放 18:00—20:00。
- **多档金额与多档比例**：住院起付线按医院等级递增（300/600/1000）而报销比例递减
  （85%/75%/60%），两组数字方向相反，容易对调。
- **易混日期序列**：电动车临时标识申领截止 2026-12-31、过渡期结束 2027-06-30、
  新规全面施行 2027-07-01。
- **废止值与现行值并存**：医保门诊起付线由 150 元调整为 200 元，公积金租房提取年度限额由
  12000 元提高到 14400 元，旧值在文中明确标注已废止，用于检查模型是否采用现行标准。
- **跨文档关联**：宠物粪便投放同时出现在垃圾分类与养犬规定；电动车充电同时出现在电动车办法、
  物业规范与用电用气手册；防汛挡水板由物业负责，在应急提示与物业规范之间跨越。
- **无答案问题**：故意提问语料中不存在的事实，检查模型是否编造。

## 使用方式

1. 新建一个只用于验收的知识库，命名带 `acceptance` 或日期后缀，与演示数据隔离。
2. 将 `corpus/` 内 12 个文件一次性上传并等待全部解析完成（PDF 与 DOCX 解析耗时明显更长）。
3. 按 `expected-answers.md` 逐题提问，记录命中文档、引用片段、回答正确性和响应时间。
4. 验收完成后删除测试知识库，避免虚构事实污染其他会话。

重新生成二进制文件：

```bash
uv run --with python-docx --with reportlab scripts/generate-knowledge-samples.py
```

该脚本只重写 `03-medical-insurance-guide.pdf` 与 `04-housing-fund-guide.docx`，
其余 10 份文本语料直接维护在 `corpus/` 目录内。
