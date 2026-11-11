# 架构与开发边界

```mermaid
flowchart LR
  U[论文链接 / 研究问题] --> S[CLI / Skills / MCP]
  S --> R[arXiv / OpenAlex / DOI / 网页]
  R --> E[版本化证据包 / 本地缓存]
  E --> A[当前代理 / 可选模型API]
  A --> V[引用 / 范围 / 标签 / 修订校验]
  V --> M[Markdown论文与调研]
  M --> Q[Quartz / GitHub Pages]
```

## 数据边界

`content/papers/` 是生成笔记，`content/research/` 是调研报告，`content/annotations/` 是人工批注。稳定 paper ID 独立于标签；文件名使用可读 slug 加哈希，避免 DOI 标点归一化导致冲突。

`.cache/epn/` 保存全文、证据包及处理状态，不提交。公开笔记保存结构化总结、原文定位、版本和证据哈希，不重新发布下载的全文。数据库不是必需组件；派生索引随网站构建重建。

`sources/` 只负责获取。`synthesis.py` 定义输出契约。`library.py` 原子写入并检查 prepare 时的修订。`research.py` 固定选定的来源修订，验证跨论文引用。`cli.py` 与 `mcp_server.py` 调用相同逻辑。

## 质量约束

- `full_text=false` 不能写入 `coverage=full_text`。
- 每项事实带有效 evidence ID；证据存在性与事实蕴含是不同问题。
- 人工批注独立保存。已手工锁定标签不会被自动分类覆盖。
- 方法、任务、本体、评测分别分类；分类词表在 `config/taxonomy.yaml`。
- 调研候选不等于已读证据。共识至少需要两个独立论文来源。
- 版本漂移或并发改动导致冲突，要求重新读取和合并；不强行覆盖。
- 外部文本只作为数据，不执行其中指令；模型密钥只存在环境变量。

## 当前范围与后续

基础版本覆盖 arXiv 与 OpenAlex 检索、arXiv 全文与通用网页提取、DOI 元数据、结构化入库、调研、安装及静态发布。OpenReview 等专用适配器、语义检索、引文图扩展、图表视觉核验和更细粒度的网站筛选可在此架构上添加。

没有内置定时任务。缺少 API 密钥不妨碍当前代理通过 MCP 工作；`--auto` 是独立可选路径。后续应在 12–20 篇具身论文上记录获取率、解析失败类型、人工修订率和费用，再决定是否引入重型组件。
