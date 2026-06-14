# Coding Agent 使用指南

> 目标：帮助项目成员理解可选的 Coding Agent 工具、模型接入方式和协作边界，方便大家根据自己的环境选择合适方案。

如果你还没有下载项目，先看 [Git 小白协作指南](./GIT_WORKFLOW.md)。

---

## 一、先区分三个概念

后面所有工具都按这三个层次理解，避免把名字混在一起。

| 层次 | 含义 | 例子 |
|---|---|---|
| Coding Agent | 真正操作项目的工具，可以读代码、改文件、运行命令或生成 PR | Trae、CodeBuddy、Claude Code、Codex |
| Coding Plan | 模型厂商提供给编码工具使用的套餐、额度或接入方案 | GLM Coding Plan、Kimi Code、MiniMax Token Plan |
| 模型 | Coding Agent 背后实际调用的大模型 | Claude Opus / Sonnet / Haiku、GLM-5.1、MiniMax-M2.7、Kimi coding model |

简单说：

- **Agent 是执行工具。**
- **Coding Plan 是套餐和接入方式。**
- **模型是实际能力来源。**

---

## 二、工具选项总览

| 工具 | 形态 | 是否有图形界面 | 大陆访问便利性 | 项目接入状态 | 适合场景 |
|---|---|---|---|---|---|
| [Trae CN](https://www.trae.cn/) | AI IDE / 图形界面 | 有 | 较高 | 观望，可选 | 新成员打开本地项目、阅读代码、修改文档或小范围代码 |
| [腾讯 CodeBuddy IDE](https://www.codebuddy.ai/docs/zh/ide/Introduction) | AI IDE / 图形界面 | 有 | 较高 | 观望，可选 | 希望使用图形化工作台完成需求、代码、预览、部署等流程 |
| Claude Code | 命令行 Coding Agent | 无，另有编辑器扩展 | 取决于模型接入方式 | 可选 | 有命令行基础，想用 Claude 或国内模型做较深入代码修改 |
| Codex | Codex App / CLI / 云端 Agent | App 有，CLI 无 | 取决于 OpenAI 账号与网络环境 | 可选 | 多任务并行、代码审查、复杂重构、长期任务跟进 |

说明：

- 表格用于说明工具形态和使用条件，不把某个工具设为统一入口。
- 网页聊天模型可以辅助理解问题，但本项目代码修改更依赖能打开仓库、查看 diff、修改文件的 Coding Agent。

---

## 三、[Trae CN](https://www.trae.cn/)

Trae CN 是图形界面的 AI IDE，适合希望直接打开本地项目文件夹的成员。

适合处理：

- 阅读 `README.md`、`docs/` 下的说明文档。
- 修改 Markdown 文档。
- 按模板补充 Skill 或小范围代码。
- 根据报错定位相关文件。
- 对一次小范围改动做解释和整理。

使用方式：

1. 打开 Trae CN。
2. 打开本地项目文件夹 `AI_Renaissance`。
3. 让 Trae 先阅读 `README.md`、`docs/GIT_WORKFLOW.md` 和任务相关文件。
4. 说明本次希望修改的文件范围。
5. 修改后查看文件清单、变更说明和 Git diff。

在工具已打开项目后，可以这样说明任务边界：

```text
你现在在 AI_Renaissance 项目里工作。
请先阅读 README.md、docs/GIT_WORKFLOW.md，以及我这次任务相关的文件。

本次任务范围是：[写清楚你要改什么]

请先说明你的修改计划。
如果你认为需要修改任务范围外的文件，请先说明原因。
改完后请列出：
1. 修改了哪些文件
2. 每个文件为什么改
3. 我应该如何检查 git diff
```

---

## 四、[腾讯 CodeBuddy IDE](https://www.codebuddy.ai/docs/zh/ide/Introduction)

CodeBuddy IDE 是腾讯提供的图形化 AI 编程工具，官方文档中包含 IDE、插件和 CLI 等形态。IDE 形态更适合希望通过图形界面完成代码修改、预览或部署流程的成员。

适合处理：

- 从需求描述生成代码草稿。
- 阅读和解释项目结构。
- 修改文档、配置或简单代码。
- 对带界面的任务做预览。
- 在腾讯生态模型和工具链中完成开发。

使用方式和 Trae 类似：

1. 打开项目文件夹。
2. 先让工具阅读项目说明和任务文件。
3. 小范围修改。
4. 检查 diff。
5. 按 Git 工作流提交 PR。

---

## 五、Claude Code

Claude Code 是 Anthropic 官方的命令行 Coding Agent。它可以在本地仓库中读取文件、修改代码、运行命令，并通过自然语言完成开发任务。

它的特点：

- 命令行使用，需要 Node.js、Git 和终端基础。
- 可使用 Anthropic 官方 Claude 模型；账号、订阅和网络条件需要自行确认，通常需要科学上网。
- 也可以通过 Anthropic-compatible 接口接入部分国内模型。
- 适合较复杂的代码理解、重构、排错和多文件修改。

### Claude 官方模型

模型版本变化很快，以下信息只作为 2026-05-02 的参考。实际使用前请查看 Anthropic 官方模型文档和 Claude Code 的 `/model` 列表。

| Claude Code 模型别名 | 当前含义（以官方文档为准） | 适合场景 |
|---|---|---|
| `opus` | 最新 Opus 系列，官方文档显示 Anthropic API 上当前解析到 Opus 4.7 | 复杂推理、复杂重构、长链路规划 |
| `sonnet` | 最新 Sonnet 系列，官方文档显示 Anthropic API 上当前解析到 Sonnet 4.6 | 日常编码、代码解释、常规修改 |
| `haiku` | 最新 Haiku 系列 | 简单任务、快速问答、轻量修改 |
| `opusplan` | Claude Code 官方特殊别名：规划阶段用 Opus，执行阶段用 Sonnet | 先规划再落地的复杂任务 |

更稳妥的写法是使用别名，例如 `sonnet`、`opus`，因为 Claude Code 会随官方更新调整别名指向。需要固定版本时，再使用完整模型名。

---

## 六、Claude Code 接国内模型

这部分是进阶内容，核心逻辑是让 **Claude Code 这个 Agent** 通过不同厂商的 Anthropic-compatible 接口调用国内模型。

| 厂商 | Agent | Coding Plan / 接入方案 | 当前模型示例（注意时效性） | 说明 |
|---|---|---|---|---|
| Kimi / Moonshot | Claude Code | Kimi Code | `kimi-for-coding` | 官方文档提供 Claude Code 和 Roo Code 的接入方式 |
| 智谱 GLM | Claude Code | GLM Coding Plan | `glm-5.1`、`glm-5-turbo`、`glm-4.5-air` | 官方文档提供 Claude Code 接入方式；GLM-5.1 需要按文档配置模型映射 |
| MiniMax | Claude Code | MiniMax Token Plan | `MiniMax-M2.7` | 官方文档提供中国区和国际区 Anthropic Base URL |
| 小米 MiMo | Claude Code 或兼容工具 | 以官方/社区接入文档为准 | 以最新文档为准 | 可作为观察项，落地前先验证稳定性、限额和兼容性 |

注意：

- **Coding Plan 表示套餐或接入方案，Agent 表示执行工具。**
- **模型版本会频繁更新，文档里出现具体版本时都要看日期。**
- **团队文档里应把厂商、套餐、模型分开表述。**
- 配置前先确认操作系统路径、API Key、Base URL、模型名和费用规则。

---

## 七、Codex

Codex 是 OpenAI 的 Coding Agent 产品线，可以通过多个入口使用：

| 入口 | 形态 | 适合场景 |
|---|---|---|
| Codex App | 图形界面 | 多任务并行、长任务跟进、同时管理多个 Agent |
| Codex CLI | 命令行 | 在本地终端中读写项目、运行命令、快速修改代码 |
| Codex Cloud | 云端 Agent | 连接 GitHub 仓库、在云端环境中完成任务并生成 PR |
| IDE 扩展 | 编辑器插件 | 在 VS Code、Cursor、Windsurf 等编辑器内使用 |

在本文中提到 Codex 时，指整个 Codex 产品线；只有讨论图形界面时才单独说 Codex App。

Codex 的使用条件与 OpenAI 账号、订阅、网络环境相关。项目成员可以根据自己的环境选择是否使用，把它作为可选入口之一即可。

---

## 八、让 Agent 改代码时的协作边界

无论使用哪个工具，都建议先把任务边界说清楚。这样可以减少误改框架、误删文件、误提交分支的风险。

通用任务边界说明：

```text
请先阅读本项目 README.md 和任务相关文件。

本次任务范围是：[写清楚你要改什么]

请先给出修改计划。
如果你认为需要修改任务范围外的文件，请先说明原因。
修改后请列出文件清单和检查方式。

请避免执行高风险 Git 操作，例如 git reset、git checkout --、git push --force。
```

专家组成员可以补充：

```text
我的任务集中在专家分析逻辑、Skill 内容或指定 Agent 内容。
如果你发现框架、仲裁层、主流程调度或数据源封装需要调整，请整理成建议。
```

---

## 九、建议工作流程

1. 按 [Git 小白协作指南](./GIT_WORKFLOW.md) 从 `main` 新建自己的临时分支。
2. 用自己选择的 Coding Agent 打开项目文件夹。
3. 让 Agent 阅读项目说明、团队分工和任务相关文件。
4. 写清楚本次任务边界。
5. 让 Agent 小步修改。
6. 每次修改后检查文件清单和 diff。
7. 确认后提交 commit。
8. 发 PR 到 `main`。

---

## 十、资料来源

本章整理时间：2026-05-02。涉及模型版本和套餐规则的内容具有时效性，以各官方文档最新页面为准。

- Trae 官网：<https://www.trae.cn/>
- 腾讯 CodeBuddy 文档：<https://www.codebuddy.ai/docs/zh/ide/Introduction>
- Codex 产品页：<https://openai.com/codex>
- OpenAI Codex 文档：<https://platform.openai.com/docs/codex>
- Claude Code 文档：<https://code.claude.com/docs>
- Anthropic Claude Code 模型配置：<https://code.claude.com/docs/en/model-config>
- Anthropic 模型总览：<https://docs.anthropic.com/en/docs/models-overview>
- Kimi Code 文档：<https://www.kimi.com/code/docs/en/>
- 智谱 GLM Coding Plan 文档：<https://docs.bigmodel.cn/cn/coding-plan/tool/claude>
- MiniMax Token Plan 文档：<https://platform.minimax.io/docs/token-plan/claude-code>
