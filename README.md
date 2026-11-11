# Embodied Paper Notes

面向具身智能的论文笔记与主题调研工作台。Markdown 是内容源；Quartz 提供静态网站；Python CLI 和本地 MCP 提供检索、证据读取、分类、入库与跨论文调研。项目文档和状态保留在仓库，不使用 Notion。

[网站](https://wenweilin2004.github.io/embodied-paper-notes/) · [管线设计](docs/pipeline-design.md) · [架构](docs/architecture.md) · [Skills/MCP 生态](docs/ecosystem.md) · [开源复用记录](docs/upstream.md)

## 能做什么

- 输入 arXiv ID/链接、DOI 或支持元数据的论文网页，获取可用原文，记录版本和获取范围。
- arXiv / OpenAlex / Crossref / Semantic Scholar 检索，支持多源并行、版本感知去重、引用图与明确的来源失败状态。
- 证据 ID 约束的中文总结，具身任务/方法/本体/评测分类，独立个人批注。
- 从已入库论文生成有引用的比较、共识、分歧与研究缺口报告；生成具身评测条件矩阵和复现准备清单。
- 阅读队列保存筛选状态与理由；离线检索笔记和原文证据；真实元数据导出 BibTeX / CSL-JSON。
- CLI、28 个 stdio MCP 工具、3 个资源、4 个工作流 Prompt 和 8 个可安装 Skill 共用验证逻辑。
- 全文缓存不入 Git；笔记和报告随仓库同步，GitHub Actions 校验并发布 Pages。

## 四个顶层工作流

当前选定以下四条 pipeline，完整边界见 [管线设计](docs/pipeline-design.md)：

- `paper-summary`：给定论文链接，读取、总结、分类并入库；主要使用 `paper-ingest`。
- `topic-research`：围绕问题检索、筛选、阅读并形成有证据的主题报告；主要使用 `paper-research`，将 `paper-discover` 和 `paper-compare` 作为内部步骤。
- `related-work`：从论文或研究问题扩展相关工作，给出关联理由和候选阅读队列；主要使用 `paper-discover`。
- `library-curation`：检索与检查已有文库，整理分类、重复或版本问题，保护人工批注并按请求同步；主要使用 `library-maintain`。

下文的 8 个 Skills 是可组合的部件，不代表 8 条顶层 pipeline。当前由 Agent 按 Skill 调用现有 MCP/CLI 完成步骤；四个名称是设计入口，统一执行器仍待实现，本轮不开发执行器。

## 安装

需要 Python 3.11+；网站还需要 Node.js 24 和 npm。先 clone：

```sh
git clone https://github.com/WenweiLin2004/embodied-paper-notes.git
cd embodied-paper-notes
```

Windows PowerShell：

```powershell
./scripts/install.ps1 -Client codex
```

macOS / Linux：

```sh
sh scripts/install.sh codex
```

脚本建立项目 `.venv`，安装 Python 包，并安装项目级 Skills/MCP。完成后重启客户端或重新加载项目。Codex 需要信任这个项目才能加载项目配置。可将参数换成 `claude` 或 `generic`；后者生成通用 `.mcp.json`，需导入支持 stdio 的客户端。

手动安装或只使用工具包：

```sh
python -m pip install -e '.[dev]'
epn --root . install --client codex --dry-run
epn --root . install --client codex
epn doctor
```

包也支持 `pip install git+https://github.com/WenweiLin2004/embodied-paper-notes.git`，或 `uv tool install git+https://github.com/WenweiLin2004/embodied-paper-notes.git`。独立内容库用 `epn init PATH` 创建；完整网站仍从本仓库 clone。

默认安装到项目，不更改用户全局配置。需要全局发现时显式运行 `epn install --client codex --scope user`。安装器保留其他 MCP 条目；遇到不同的现有配置会停止，避免静默覆盖。路径移动或新电脑需重新安装客户端配置。

升级已安装的仓库技能时，先查看本地改动，再执行 `epn install --client codex --force`；这会更新打包的 Skill 文件，不覆盖其他 MCP 条目。`epn capabilities` 返回实际安装能力。

## Skills 与 MCP 组合

`research-orchestrator` 负责四个入口之间的路由；其余技能按需要作为步骤或辅助能力使用，比较、复现准备和引用导出不新增顶层 pipeline。

- `research-orchestrator`：研究总入口，按问题组合下列技能，记录范围和不足。
- `paper-discover`：多源检索、引文追踪、候选筛选与阅读队列。
- `paper-ingest`：读原文、分类、带证据总结与入库。
- `paper-research`：跨论文综述、共识、分歧和研究缺口。
- `paper-compare`：具身任务、本体、数据、动作表示与评测条件比较。
- `paper-reproduce`：复现所需条件、已报告证据与缺失信息清单。
- `citation-manager`：从已保存元数据导出文献引用。
- `library-maintain`：本地搜索、重复或版本检查、质量检查和受修订保护的批注维护。

例如：

> 使用 research-orchestrator，调研 VLA 跨本体泛化；先检索和筛选，精读相关论文，比较实验条件，保存有引用的报告并导出 BibTeX。

可选外部 MCP 按需配置，核心功能不依赖它们：

```sh
epn integrations list
epn integrations install arxiv --client codex --dry-run
epn integrations install arxiv --client codex
epn integrations install github --client codex --dry-run
```

arXiv 扩展需要已有 `uvx`，可补充原始 LaTeX 等能力；GitHub 扩展使用官方 Docker MCP，以只读模式查找实现，需要 Docker 和客户端环境中的 `GITHUB_PERSONAL_ACCESS_TOKEN`。去掉 `--dry-run` 才会写客户端配置；不会把密钥值写入配置。第三方包或镜像由对应运行时首次启动时下载，安装器不声称已经启动验证。若客户端已有这些 MCP，可直接复用，无需重复注册。详见 [生态与外部集成](docs/ecosystem.md)。

## 单篇论文

安装 Skill/MCP 后，可在客户端说：

> 使用 paper-ingest，将这篇论文加入本库：论文链接。总结方法、实验条件和局限，并自动分类。

CLI 等价流程：

```sh
epn ingest https://arxiv.org/abs/2406.09246v1
# 输出 packet_path、完整证据和 allowed_tags；让当前代理按 Skill 生成 summary.json
epn commit <packet_path> <summary.json>
epn validate
```

证据 JSON 在 `.cache/epn/packets/`；原文分段可通过 MCP 分页读取。总结 JSON 规范见 [paper-ingest](skills/paper-ingest/references/summary-format.md)。只取得摘要时，只能标记摘要阅读范围；引用校验检查来源存在，不代表模型结论已经科学审定。

## 主题调研

```sh
epn research discover 'VLA 的跨本体泛化' --query '"vision language action" AND "cross embodiment"' --provider arxiv --limit 10
# 选择候选并完成单篇入库后，用稳定 paper IDs 准备调研包
epn research prepare 'VLA 的跨本体泛化' --papers '<paper-id-1>,<paper-id-2>'
epn research commit <report.json>
```

也可直接使用 `paper-research` Skill。它会记录检索策略、筛选候选、读原文并比较可比的实验条件。[报告 JSON 规范](skills/paper-research/references/research-format.md)。共识陈述至少要引用两篇论文；未知引用和已过期的来源修订会被拒绝。

```sh
epn search 'vision language action' --provider all --limit 5
epn queue add candidates.json --reason '候选：跨本体评测'
epn queue list --status candidate
epn find 'generalization' --tags method/vla
epn research compare '跨本体评测条件比较' --papers '<id-1>,<id-2>'
epn research reproduce '<id-1>'
epn citations --papers '<id-1>,<id-2>' --format bibtex --output references.bib
```

`candidates.json` 可以是 search 的 JSON 列表、多源返回的 `papers` 对象或 discover 的 `candidates` 包。队列在 `data/reading-queue.json`，可随 Git 同步；状态修改需带 `list_queue` 返回的 revision。compare/reproduce 只准备证据与缺失项，不声称数值可比或实验已经复现。继续读取原文并通过 `commit_research` 保存有证据的报告。普通建议和未知项不要伪装成论文事实。

报告可另带 `planning`：`open_questions` 保存待核实问题，`proposed_steps` 保存拟议步骤和验收标准，`assumptions` 保存工作假设。它们会标记为“规划备注（非论文事实）”，不替代事实章节的证据引用，也不表示实验已执行。

## 可选 API 自动模式

默认 Skill/MCP 模式使用当前代理，无需额外模型 API 密钥。无人值守模式支持带 JSON mode 的 OpenAI-compatible Chat Completions 接口，显式设置 `EPN_MODEL`、`EPN_API_KEY`，可选 `EPN_BASE_URL`（默认 `https://api.openai.com/v1`）：

```sh
epn ingest <paper-url> --auto
epn research auto <research-packet.json>
```

密钥只放进本机环境变量或 CI Secrets。自动模式会产生模型调用费用；不会在缺配置时偷偷选模型，也不重试可能计费的请求。上下文超过 `EPN_MAX_INPUT_CHARS`（默认 120000 字符）会明确报错，改用分章节 Skill 阅读，不静默截断全文。

默认 PDF 用轻量解析。可选 `pip install -e '.[pdf]'` 安装 Docling，并显式指定 `epn ingest <url> --pdf-parser docling`；首次使用可能下载模型权重。复杂表格、公式和图像仍须人工或视觉核验。

## 网站与多电脑同步

```sh
cd site
npm ci
npm run build
npm run dev
```

笔记在根 `content/`，不是 `site/content/`。Pages 的项目路径已设为 `wenweilin2004.github.io/embodied-paper-notes`。`status: ai-draft` 表示未经人工复核，仍会公开显示；不要把它当访问控制。

开始工作前 `git pull`，结束后提交笔记并 `git push`。MCP 不替用户执行 push；推送到 main 后 Actions 校验并部署。两台电脑同时改同一文件仍可能出现 Git 冲突。缓存和本地客户端配置不随 Git 同步；完整原文可重新获取。

## 开发与验证

```sh
python -m pytest
epn validate
python -m build
```

测试覆盖身份与版本解析、HTML/PDF 回退、证据引用、摘要范围、修订冲突、人工注释保护、研究引用、安装幂等性和真实 MCP stdio 握手。网络提供方和可选模型会变化；测试不代表全文解析或总结准确率的通用保证。

项目自有代码 MIT。实际复制/改编的 Quartz 和 arXiv 模块保留原许可与固定 commit；详见 [复用记录](docs/upstream.md)。
