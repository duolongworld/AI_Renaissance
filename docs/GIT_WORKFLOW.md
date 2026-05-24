# Git 协作指南

> 核心原则：**main 是唯一长期主线，所有变更通过 PR 合入 main。**

---

## 一、分支策略

```
main (唯一长期主线，受 branch protection 保护)
 ├── feat/xxx   ← 临时开发分支，服务单个任务，合并后删除
 ├── fix/xxx    ← 临时修复分支，合并后删除
 ├── docs/xxx   ← 临时文档分支，合并后删除
 └── tag: v0.1.0-beta, v0.2.0, ... ← 版本发布
```

**核心规则：**

1. **main 是唯一长期主线**，也是用户默认入口
2. **不长期维护 develop**，不设集成分支
3. **临时开发分支只服务一个任务**，合并后立即删除
4. **所有变更通过 PR 回 main**，CI 必须通过
5. **版本用 tag / GitHub Release 表达**，包括 beta

---

## 二、工作流程

### 完整流程

```
1. git checkout main && git pull origin main
2. git checkout -b feat/your-name-task-name
3. 开发、提交
4. git push origin feat/your-name-task-name
5. 在 GitHub 创建 PR → base: main
6. CI 通过 + 至少一人 Review → 合并
7. 删除临时分支
8. 打 tag（如需发布）
```

### 分支命名

| 类型 | 命名 | 示例 |
|---|---|---|
| 功能 | `feat/owner-task` | `feat/xiaopi-macro-layers` |
| 修复 | `fix/owner-desc` | `fix/huangtang-gbk-encoding` |
| 文档 | `docs/owner-desc` | `docs/cat-git-workflow` |
| 重构 | `refactor/owner-desc` | `refactor/pkm-arbitration-v2` |
| Skill | `skill/owner-name` | `skill/tao-crowding-state` |
| Agent | `agent/owner-domain` | `agent/xixi-macro-v2` |
| 发布 | `release/vX.Y.Z` | `release/v0.2.0` |

---

## 三、PR 规则

### PR 目标分支

**统一使用 `main` 作为 base 分支。** 不再向 develop 提 PR。

### PR 模板

```markdown
## 类型

feat / fix / docs / refactor / skill / agent / release

## 做了什么

-
-

## 如何测试

写明你怎么确认它能用。

## 影响范围

改了哪些文件？会影响哪些组？

## Checklist

- [ ] 我是在自己的临时分支上开发的
- [ ] 我没有直接提交到 main
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

## 四、CI & Branch Protection

### CI（GitHub Actions）

每次 PR 自动运行：
- `pytest` 测试（41 用例）
- 模块导入检查

### Branch Protection（main 分支）

- **禁止直接 push** — 必须通过 PR
- **CI 必须通过** — 测试全绿才能合并
- **至少 1 人 Review** — 代码审查后才能合并
- **禁止 force push** — 保护历史完整性

---

## 五、版本发布

### 语义化版本

```
vMAJOR.MINOR.PATCH[-suffix]

示例：
  v0.1.0-beta    ← 首个 beta 版本
  v0.1.0         ← 首个正式版本
  v0.2.0         ← 功能更新
  v1.0.0         ← 重大版本
```

### 发布流程

```bash
# 1. 确保 main 是最新的
git checkout main && git pull origin main

# 2. 打 tag
git tag -a v0.1.0-beta -m "Beta release: 8 Agent + N Skill 架构验证"

# 3. 推送 tag
git push origin v0.1.0-beta

# 4. 在 GitHub 创建 Release（附 changelog）
```

### 当前版本

| 版本 | 状态 | 日期 | 说明 |
|------|------|------|------|
| v0.1.0-beta | 当前 | 2026-05-24 | 8 Agent + N Skill 架构，3 个 Agent 产出真实信号 |

---

## 六、与旧策略的变化

| 维度 | 旧策略 | 新策略 |
|------|--------|--------|
| 长期分支 | main + develop | **仅 main** |
| 开发入口 | 从 develop 拉分支 | **从 main 拉临时分支** |
| PR 目标 | develop | **main** |
| 集成测试 | develop 上手动 | **CI 自动** |
| 版本表达 | 无 | **tag + GitHub Release** |
| develop 分支 | 长期保留 | **归档，不再维护** |

---

## 七、第一次下载项目

```bash
git clone https://github.com/duolongworld/AI_Renaissance.git
cd AI_Renaissance
# 默认就在 main 分支
```

---

## 八、最小完整流程

```bash
# 开始新任务
git checkout main && git pull origin main
git checkout -b feat/your-name-task

# 开发、提交
git add 你修改的文件
git commit -m "feat: 说明你做了什么"
git push origin feat/your-name-task

# 在 GitHub 创建 PR → base: main
# CI 通过 + Review → 合并
# 删除临时分支
```

---

## 九、Skill 专家版最小流程

```bash
git checkout main && git pull origin main
git checkout -b skill/your-name-skill-name

# 只修改相关 Skill 文件
git add skills/financial/xxx/SKILL.md
git commit -m "feat: 添加 xxx Skill"
git push origin skill/your-name-skill-name

# 创建 PR → base: main
```

---

## 十、千万不要做

- ❌ 直接推送到 `main`
- ❌ 长期保留临时开发分支
- ❌ 使用 `git push --force`
- ❌ 提交 `.env`、API key、密码、大型数据文件
- ❌ 在自己的分支上 merge main（应 rebase）

---

## 十一、常见问题

### Q：develop 分支还在吗？

develop 分支已归档，不再维护。所有新工作从 main 拉临时分支，PR 直接回 main。

### Q：我的旧 PR 目标是 develop 怎么办？

在 GitHub 上将 base 分支改为 main 即可。

### Q：怎么回退？

通过 tag 回退：`git checkout v0.1.0-beta`

### Q：CI 挂了怎么办？

本地运行 `pytest tests/ -v`，修复后再 push。

---

*最后更新：2026-05-24*
