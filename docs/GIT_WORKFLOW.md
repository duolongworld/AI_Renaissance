# Git 小白协作指南

> 目标：让你安全地把自己的代码/文档交上来，不影响别人，也不直接改 `main` / `develop`。

你不需要一开始学会 Git 的所有概念。先记住一句话：

> 每次都从 `develop` 拉最新代码，然后在自己的分支上开发，最后通过 PR 合并。

---

## 一、分支关系

```
main        ← 稳定分支，不要直接改
 └─ develop ← 集成分支，大家的代码最终先合到这里
      └─ 你的分支 ← 你自己的开发分支，只改自己的任务
```

你平时只需要关心两件事：

1. 从 `develop` 创建自己的分支。
2. 做完后把自己的分支提交 PR 到 `develop`。

---

## 二、Windows 第一次准备环境

### 1. 安装 Git

打开 Git for Windows 官方下载页：

```text
https://git-scm.com/install/windows
```

下载 Windows 版本安装包。安装时一路默认即可。

安装完成后，**重新打开 PowerShell**，输入：

```powershell
git --version
```

如果能看到类似下面的版本号，说明安装成功：

```text
git version 2.xx.x.windows.x
```

如果提示：

```text
git 不是内部或外部命令
```

说明 Git 没装好，或者安装后没有重新打开 PowerShell。

### 2. 选择开发目录

建议把项目放在桌面或文档目录，不要放在 `C:\Program Files`、`C:\Windows` 这类需要管理员权限的目录。

推荐：

```powershell
cd $HOME\Desktop
```

或者：

```powershell
cd $HOME\Documents
```

---

## 三、第一次下载项目

小白推荐使用 HTTPS，不需要先配置 SSH key。

### 情况A：你有主仓库写权限

如果你是项目团队成员，并且维护者已经给你仓库权限，可以直接克隆主仓库：

```powershell
git clone https://github.com/duolongworld/AI_Renaissance.git
cd AI_Renaissance
```

然后切换到 `develop`：

```powershell
git checkout develop
git pull origin develop
```

### 情况B：你没有主仓库写权限

如果你是外部贡献者，或者 push 时提示没有权限，先在 GitHub 页面 Fork 本仓库，再克隆你自己的 Fork。

```powershell
git clone https://github.com/你的GitHub用户名/AI_Renaissance.git
cd AI_Renaissance
```

后续仍然从 `develop` 新建分支，最后在 GitHub 上发 PR 到主仓库的 `develop`。

---

## 四、每次开始开发前

每次开始写代码前，先更新本地 `develop`：

```powershell
git checkout develop
git pull origin develop
```

然后从最新的 `develop` 创建你自己的分支。

---

## 五、新建自己的分支

不要直接在 `develop` 上写代码。

新建分支：

```powershell
git checkout -b docs/zhangsan-git-guide
```

分支命名建议使用英文或拼音，不建议使用中文。

常见命名：

| 类型 | 分支名示例 | 适用场景 |
|---|---|---|
| 文档 | `docs/zhangsan-git-guide` | 改文档 |
| Agent | `agent/lisi-cash-flow` | 写 Agent |
| Skill | `skill/wangwu-financial-report` | 写 Skill |
| 修复 | `fix/zhaoliu-debug-ui` | 修 bug |
| 功能 | `feature/qianqi-signal-check` | 通用功能 |

---

## 六、修改文件后先检查状态

每次提交前都先看：

```powershell
git status
```

它会告诉你：

- 你改了哪些文件
- 哪些文件还没加入提交
- 当前在哪个分支

如果你发现自己在 `develop` 或 `main` 上，请先停下来，不要提交。

---

## 七、提交代码

只添加你这次改过的文件，不要一股脑全部添加。

### 例子1：提交文档

```powershell
git add docs/GIT_WORKFLOW.md
git commit -m "docs: 完善 Windows Git 入门流程"
```

### 例子2：提交 Agent

```powershell
git add agents/research/financial/cash_flow/
git commit -m "feat: 添加现金流验证 Agent"
```

### 例子3：提交 Skill

```powershell
git add skills/financial/cash_flow_quality_check/SKILL.md
git commit -m "feat: 添加现金流质量检查 Skill"
```

提交信息建议格式：

```text
docs: 修改文档
feat: 新增功能
fix: 修复问题
refactor: 重构代码
test: 添加测试
```

---

## 八、推送到 GitHub

把你的分支推送到远端：

```powershell
git push origin docs/zhangsan-git-guide
```

把上面的分支名换成你自己的分支名。

如果 GitHub 弹出登录窗口，按提示登录即可。

如果推送失败，并提示需要用户名、密码或 token，不要慌，先在群里问；也可以使用 GitHub CLI 登录：

```powershell
gh auth login
```

---

## 九、创建 PR

推送成功后，打开 GitHub 项目页面，通常会看到：

```text
Compare & pull request
```

点进去后确认：

```text
base: develop
compare: 你的分支
```

然后填写 PR 说明，创建 PR。

---

## 十、PR 模板

可以直接复制：

```markdown
## 类型

Docs / Agent / Skill / Fix / Feature

## 做了什么

- 
- 

## 如何测试

写明你怎么确认它能用。

## 影响范围

改了哪些文件？会影响哪些组？

## Checklist

- [ ] 我是在自己的分支上开发的
- [ ] 我没有直接提交到 main / develop
- [ ] 我只提交了和本任务相关的文件
- [ ] 我没有提交 .env、密钥、日志、大型数据文件
- [ ] 我已经运行或人工检查过结果

## 如果这次提交的是 Skill

- [ ] Skill 路径符合 `skills/{domain}/{skill_name}/SKILL.md`
- [ ] 只修改了本次任务相关的 Skill 或文档
- [ ] 没有修改 `agents/signal.py`、`agents/base.py` 或仲裁层代码
- [ ] 写清楚了必填输入、可选输入和缺失处理
- [ ] 写清楚了证据规则和人工复核条件
```

---

## 十一、常用命令速查

| 场景 | 命令 |
|---|---|
| 查看当前状态 | `git status` |
| 切到 develop | `git checkout develop` |
| 更新 develop | `git pull origin develop` |
| 新建分支 | `git checkout -b docs/your-name-task` |
| 添加文件 | `git add 文件路径` |
| 提交 | `git commit -m "docs: 说明你做了什么"` |
| 推送 | `git push origin 你的分支名` |
| 查看分支 | `git branch` |

---

## 十二、千万不要做

不要直接推送到 `main`：

```powershell
git push origin main
```

不要直接推送到 `develop`：

```powershell
git push origin develop
```

不要随便使用这些危险命令：

```powershell
git reset --hard
git push --force
```

不要提交这些内容：

- `.env`
- API key / token / 密码
- `__pycache__/`
- `logs/`
- 临时下载文件
- 大型原始数据
- 和本次任务无关的文件

---

## 十三、常见问题

### Q1：提示 `git 不是内部或外部命令`

说明 Git 没装好，或者安装后没有重新打开 PowerShell。

解决：

1. 重新安装 Git for Windows
2. 关闭并重新打开 PowerShell
3. 再运行：

```powershell
git --version
```

### Q2：`git clone` 很慢或失败

可能是网络问题。先重试一次；如果还是失败，在群里问。

### Q3：push 时要求登录 GitHub

按弹窗登录即可。

如果没有弹窗，可以尝试：

```powershell
gh auth login
```

如果你没有安装 GitHub CLI，先在群里问，不要乱输密码。

### Q4：看到 `LF will be replaced by CRLF`

这是 Windows 换行提示，一般不是错误，可以继续。

### Q5：提示冲突 conflict

先停下来，不要乱点，不要乱删。

把错误信息复制到群里，让熟悉 Git 的人帮你看。

### Q6：`git checkout develop` 提示找不到分支

先查看远端分支：

```powershell
git branch -a
```

如果看不到 `origin/develop`，先确认是否 clone 到了正确仓库，或者在群里问维护者当前集成分支名称。

### Q7：Windows 终端里中文显示乱码

项目 Markdown 文档使用 UTF-8 编码。阅读文档建议直接用 VS Code、Trae、CodeBuddy 或 GitHub 页面。

如果在 PowerShell 里查看文件乱码，可以用：

```powershell
Get-Content docs\ANALYSIS_SKILL_TEMPLATE.md -Encoding UTF8
```

---

## 十四、最小完整流程

第一次：

```powershell
cd $HOME\Desktop
git clone https://github.com/duolongworld/AI_Renaissance.git
cd AI_Renaissance
git checkout develop
git pull origin develop
git checkout -b docs/your-name-task
```

改完文件后：

```powershell
git status
git add 你修改的文件
git commit -m "docs: 说明你做了什么"
git push origin docs/your-name-task
```

最后去 GitHub 创建 PR，目标分支选择 `develop`。

---

## 十五、Skill 专家版最小流程

如果你只是在提交一个专家 Skill，可以按这个最小流程走：

```powershell
git checkout develop
git pull origin develop
git checkout -b skill/your-name-skill-name
```

通常只需要新增或修改相关 Skill 文件，例如：

```text
skills/financial/cash_flow_quality_check/SKILL.md
```

提交时只添加相关文件：

```powershell
git status
git add skills/financial/cash_flow_quality_check/SKILL.md
git commit -m "feat: 添加现金流质量检查 Skill"
git push origin skill/your-name-skill-name
```

最后在 GitHub 上创建 PR，目标分支选择 `develop`。

---

*最后更新：2026-05-02*
