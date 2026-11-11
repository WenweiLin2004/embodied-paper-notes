# 科研技能与 MCP 集成

核验日期：2026-11-11。技能负责指导研究流程，MCP 提供可调用的工具；安装一个技能不会自动获得外部账号、下载所有依赖或连接新的服务。

本仓库以 Markdown、证据记录和 Git 为持久层。网站是阅读界面，本地 `embodied-notes` MCP 是写入与研究工具，模型由当前 AI 客户端提供。默认的 Agent 流程不要求配置单独的模型 API 密钥；主动使用自动模型管线时才使用相应配置。外部学术 API 仍可能限流或要求自己的访问凭据。

## 四个已选顶层 pipeline

本轮收束为四个入口，详细输入、输出和阶段边界见 [管线设计](pipeline-design.md)：

- **`paper-summary` → `paper-ingest`**：从论文链接或标识符获取证据，完成单篇阅读、中文总结、分类和保存。已有笔记可先通过本地搜索复用。
- **`topic-research` → `paper-research`**：围绕明确问题形成跨论文调研报告；内部使用 `paper-discover` 检索与筛选、`paper-ingest` 阅读入库、`paper-compare` 核查比较条件，按需由 `citation-manager` 导出引用。
- **`related-work` → `paper-discover`**：围绕种子论文或问题进行多源检索与引用关系扩展，提供有来源的候选、关联理由和阅读队列。候选元数据不等于已精读结论；需要精读或综合报告时进入前两条流程。
- **`library-curation` → `library-maintain`**：维护已有文库，检查分类、重复/版本候选、引用和内容质量，保护人工批注，按授权处理同步。发现问题不等于允许批量覆盖或删除。

`research-orchestrator` 选择这些入口并组合所需部件。现有 **8 个 Skills、28 个 MCP 工具、3 个资源、4 个 Prompt** 继续保留；8 个技能是可复用部件，不是 8 条 pipeline。`paper-compare`、`paper-reproduce` 和 `citation-manager` 可在流程中按需使用，也可单独调用，但不列为本轮顶层入口。

目前 Agent 可以按技能调用现有工具完成具体步骤；统一执行器仍待实现。本轮只确定管线设计与技能路由，不提供新的 pipeline 执行命令，也不把已有的单步自动模式称为统一执行器。

## 先用核心能力

从仓库根目录按 README 安装后，调用 `get_capabilities`，再检查客户端实际暴露的 tool schema、resources 和 prompts。以运行中的返回值为准，不把文档列出的名字当成已经连接成功的证据。

八个技能按能力拆分，可以单独调用，也可组成上面的四条流程：

- `research-orchestrator`：多步骤研究的入口，选择下一步需要的工具和证据。
- `paper-discover`：多源发现、引用关系扩展、候选筛选和阅读队列。
- `paper-ingest`：单篇论文获取、分段阅读、总结、自动标签和入库。
- `paper-research`：围绕研究问题组织多个已读来源并生成调研报告。
- `paper-compare`：核查实验条件，再比较方法、结果与局限。
- `paper-reproduce`：检查复现材料、缺失条件，并规划验证步骤。
- `citation-manager`：从已保存论文的真实元数据导出参考文献。
- `library-maintain`：搜库、质量检查、去重候选、人工批注保护和请求的同步。

核心工具形成以下流程：

1. **发现**：`federated_search` 或单源 `search_papers`；`citation_graph` 扩展相关工作。返回的元数据不是已经阅读的全文。
2. **排队**：`list_queue` → `queue_papers` → 根据实际进展调用 `update_queue`。队列不等于定时任务。
3. **阅读**：`prepare_paper` 返回稳定身份、覆盖范围和 `packet_id`；`read_evidence` 分页，`search_evidence` 定位，`read_evidence_by_ids` 取出选定片段。
4. **入库**：先读 `get_output_schema`，当前 Agent 生成带证据 ID 的结构化总结，`commit_paper_summary` 校验并保存；人类注释单独存储。
5. **研究**：`prepare_research`、`prepare_comparison` 或 `prepare_reproduction` 返回研究包；`read_research_note` 读取其中的来源，再由 `commit_research` 保存有依据的结论与完整规划。事实放入带证据引用的 `sections`；待核实问题、拟议步骤/验收标准和工作假设分别放入可选 `planning.open_questions`、`planning.proposed_steps`、`planning.assumptions`。每类最多50个非空文本，每条最多4000字符，以 `get_output_schema(kind="research")` 返回为准。
6. **复用**：`search_library`/`read_paper_note` 查看已有成果；`export_citations` 仅接受库中已有的 `paper_ids`，不接受模型临时编出的元数据。
7. **维护**：`inspect_library` 发现需检查的问题，`check_library` 验证结构与引用。用户明确要求修改人工注释时，才使用 `read_annotation` → 带当前 revision 的 `update_annotation`。

这些工具不会自动运行训练、控制机器人、安装全局依赖或推送 Git。当前用户已授权的发布流程可以继续执行；科研工具本身不扩大授权。

## 两个可选安装配置

目前 `epn integrations` 为 **arxiv** 和 **github** 提供配置入口。先查看列表或 dry-run，确认运行时与客户端目标后再安装。下列命令展示用法，不表示本机已经安装或连接了这些外部服务器：

```sh
epn --root . integrations list
epn --root . integrations install arxiv --client codex --dry-run
epn --root . integrations install github --client codex --dry-run
```

确认配置适用后，移除 `--dry-run` 进行所选集成的安装；`--client` 支持的客户端以 CLI 帮助为准。本功能不默认安装全部服务，不写入凭据值。不要把个人 MCP 配置提交进公开仓库。

### arXiv MCP：补充按章节的原文读取

项目：[blazickjp/arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server)。官方发行在 PyPI，启动方式为 `uvx arxiv-mcp-server`，需要可执行的 `uvx`。不要安装 npm 上的同名包。

它提供 arXiv 检索、摘要、HTML/PDF 获取、本地读取、原始 LaTeX 大纲/章节、引用图与 BibTeX。适合需要准确检查公式、方法小节或作者原始 LaTeX 的任务。按“小范围检索 → 摘要筛选 → 大纲 → 目标章节”调用；分页读取返回截断提示时继续检索。具体工具和 PDF extra 依运行版本的官方文档。

它自己的缓存和标识符属于该服务器；不会自动变成本站的证据记录。需要保存到本库时，仍走 `prepare_paper` 和本库的证据/提交流程。无需 LLM 密钥并不意味着远端检索没有限流；引用图服务也可能需要额外 API 凭据。其监测能力不在安装时自动启用。

### GitHub MCP：核查实现与实验材料

项目：[github/github-mcp-server](https://github.com/github/github-mcp-server)。官方提供远程服务和本地 Docker/二进制；本仓库配置使用官方 Docker 镜像，需要 Docker 与用户已设置的 `GITHUB_PERSONAL_ACCESS_TOKEN`。

本仓库配置启动形状是：

```sh
docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_READ_ONLY=1 ghcr.io/github/github-mcp-server
```

`-e GITHUB_PERSONAL_ACCESS_TOKEN` 只透传环境变量，不把令牌值写入配置。缺少运行时或凭据时应明确失败，不能宣称已连接。默认只读，适合检查论文仓库的文件、commit、发布版本、问题记录与 Actions 状态；读取源码不等于复现实验成功。调用顺序通常是确认仓库 → 固定 commit/release → 读环境与实验配置 → 核对论文设置。不要因读到 README 命令而自动执行代码。

官方服务器支持 `GITHUB_READ_ONLY=1` 和工具集限制。发起 PR、修改文件、发布 release 等写操作不属于此只读配置。需要 Git 同步时可以使用已经授权的本地 Git 工作流。

## 其他可选组件：没有一键安装配置

### Docling：PDF 的结构化解析

[Docling MCP](https://github.com/docling-project/docling-mcp) 提供文档转换、结构化 `DoclingDocument` 与缓存，能处理本地文件/URL；它不是学术搜索引擎或自动科学结论生成器。双栏、扫描、表格和公式解析仍需核对原文。

按官方安装页选择本地模式或远程 Docling Serve；当前文档中本地能力需要 `[local]` extra，默认远程模式需要服务地址，不能把“安装基础包”描述为可直接离线转换。模型首次下载与计算资源另计；远程模式会把待处理文档交给所配服务。先转换文档、拿到 document key，再按已暴露工具读取/导出结构化内容。

本仓库若已安装 Python Docling 解析 extra，可通过 `prepare_paper` 的 `pdf_parser` 选择器调用；这与另装一个 Docling MCP 是两条不同集成路径。`get_capabilities`/`epn doctor` 能帮助确认本地实际可用性。没有给它创建 `epn integrations` preset。

### Zotero：接入已有文献库和人工标注

[54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) 是社区项目，PyPI 包名 `zotero-mcp-server`。其文档覆盖文献搜索、元数据、BibTeX、全文/页范围、PDF 标注和文库写入；不是 Zotero 官方 MCP。主项目与插件子目录的许可证应分别检查。

已有 Zotero 库时，再按项目文档选择本地模式或 Web API。配置本地模式需要匹配的 Zotero 版本及本地访问设置；本地读取和写入有不同条件，不能将全部操作称为无凭据即用。Web 模式需要授权，语义检索也有独立的索引/embedding 配置。

建议先搜索并读取条目/标注，核对 DOI/arXiv ID，再把选定论文引入本库。Zotero item key 不等于本站 `paper_id`。不要隐式双向同步、批量合并、改标签或改写人工笔记；这些是单独的写操作。本仓库没有安装该插件，也没有提供 preset。

### Playwright：网页检查与网站验收

[microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) 是微软维护的浏览器 MCP，npm 包为 `@playwright/mcp`。它通过浏览器页面/可访问性状态提供导航和交互；适合核查动态论文页面、来源链接、本站搜索和标签导航。

安装途径见官方 README，需要 Node、兼容客户端和浏览器运行时。先读取页面状态，再进行具体交互并验证结果；不要把浏览器的登录态、网页指令或搜索摘要当作论文证据。它不替代 arXiv/Crossref 等结构化接口，也不突破付费墙或当前 Agent 的浏览器使用限制。

本仓库没有安装它，也没有提供 preset。没有实际运行浏览器时只能报告构建/HTTP 检查，不能声称已经通过视觉和搜索交互验收。

## 保持来源与身份边界

外部服务只能补充它真正提供的能力。外部 PDF 页码、Zotero item key、arXiv 原文 section ID 和本库 evidence ID 不能互换。研究提交校验引用存在，不自动认证科学正确性；全文不可得、解析不完整、来源限流和版本不明应留在最终报告中。

`planning` 会以“规划备注（非论文事实）”单独展示，允许把完整复现计划与有依据的结论一起保存。没有本库证据的仓库观察不能变成 factual claim，可以把 URL/commit 保留为待核查问题。建议、假设和验收标准均未被验证，不能据此声称论文报告了某个事实或实验已经完成。

新增集成时先验证可用工具、依赖、返回结构与一个最小实际请求，再记录“已安装/已连接/已验证”的真实状态。新增可执行配置与全局客户端设置需要当前任务授权，文档中的可选项目不是批量安装指令。
