# RAGFlow 召回质量人工验收语料

本目录是一套完整的虚构业务语料，用来评估 Common Agent 经 RAGFlow 完成的解析、召回、重排、
引用和跨文档问答质量。所有组织、人员、日期、号码、指标和标记均为测试数据，不是产品配置或
真实客户信息。

## 目录结构

- `corpus/`：只上传这个目录内的 12 份文档，总正文约 2–3 万中文字符。
- `expected-answers.md`：人工提问与标准答案，禁止上传，否则会把答案直接泄漏给检索系统。
- `scripts/generate-knowledge-samples.py`：重新生成多页 PDF 和 DOCX。

语料覆盖 Markdown、TXT、PDF、DOCX，并有意设计了以下检索难点：

- “发布日期、冻结日期、试点日期”等相近时间；
- “P0/P1 服务恢复目标”和“灾难恢复 RTO”等相近指标；
- 旧规则、正式规则和临时例外并存；
- 同一项目在产品、运维、安全、验收、事故复盘和治理文档中的跨文档关联；
- 语料中不存在答案的问题，用于检查模型是否会编造。

## 使用方式

1. 新建一个只用于验收的知识库。
2. 将 `corpus/` 内 12 个文件一次性上传并等待全部解析完成。
3. 按 `expected-answers.md` 逐题提问，记录命中文档、引用片段、回答正确性和响应时间。
4. 验收完成后删除测试知识库，避免虚构事实污染其他会话。

重新生成二进制文件：

```bash
uv run --with python-docx --with reportlab scripts/generate-knowledge-samples.py
```
