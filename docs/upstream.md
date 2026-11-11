# 开源复用与许可证

## 实际纳入源码

- **Quartz**：静态网站生成器，固定来源与 commit 见 [site/THIRD_PARTY.md](../site/THIRD_PARTY.md)。保留 MIT 许可；修改站点配置、中文导航与样式、根内容目录、构建脚本。源码留在 `site/`，可独立升级。
- **arxiv-mcp-server**：原样纳入 arXiv 标识解析模块，保留 Apache-2.0 许可、原作者注释与固定来源记录。具体文件和 commit 见 [third_party/arxiv-mcp-server/PROVENANCE.md](../third_party/arxiv-mcp-server/PROVENANCE.md)。其余检索适配和库写入围绕本项目接口重新实现。

## 接口依赖

官方 Python MCP SDK 提供 stdio 协议；httpx、Beautiful Soup、Pydantic、PyYAML、pypdf 与 Typer 支持管线。可选 Docling 单独安装。它们通过标准包依赖安装，没有把整个第三方运行环境复制到仓库。

## 设计参考，没有宣称复制其实现

- [Paper Search MCP](https://github.com/openags/paper-search-mcp)：来源能力分离、统一元数据、失败降级。
- [PaperQA2](https://github.com/Future-House/paper-qa)：证据优先的回答与引用；本项目额外强制单篇范围和具身评测字段。
- [Papernook](https://github.com/affromero/papernook)：捕获、分类、归档，以及文件为事实来源。
- [Open Notebook](https://github.com/lfnovo/open-notebook)：来源与笔记分离。
- [GPT Researcher](https://github.com/assafelovic/gpt-researcher)：研究问题拆分和来源追踪。

这些大型服务端应用没有整库搬入，因为 GitHub Pages 只运行静态内容。可替换的研究管线、可安装 Skills 和本地 MCP 是本项目新增的集成层。
