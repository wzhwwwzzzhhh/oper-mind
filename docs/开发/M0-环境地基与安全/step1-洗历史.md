# M0 / Step1 — 洗历史（安全止血）

> 里程碑：M0　|　分支：`feat/m0-foundation`　|　日期：2026-07-14
> 关联：`design.md` §2.1　|　快照 commit：`8813a05`（洗历史前 WIP）

---

## Design（为什么）

`config/config.local.yaml` 含真实 DeepSeek key（`sk-0218...`），且已进 git 全部历史。仅从工作区删除无用——历史里任何一个 commit 都能翻出完整 key。必须：

1. 用户在 DeepSeek 控制台**吊销**旧 key 并换新（只有用户能做，代码侧无法止血）。
2. 从**全部历史**抹除该文件。
3. 停止跟踪，靠 `.gitignore` 防复发。

## Step（怎么做）

洗历史是不可逆的历史重写，先做防误删保护，再动手：

1. **备份本地配置**：`config.local.yaml` → 仓库外 `../config.local.yaml.backup`（本地仍需它跑程序）。
2. **提交 WIP 快照**：`8813a05`，把当时未提交的改动固化，避免重写时丢工作。
3. **抹除历史**：因未装 `git-filter-repo` 且无 pip，改用 git 自带：

```bash
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch config/config.local.yaml' \
  --prune-empty --tag-name-filter cat -- --all
```

4. **清引用 + gc**：删 `refs/original/`、`reflog expire`、`gc --prune=now`，让旧对象真正落地删除。
5. **停跟踪**：`git rm --cached config/config.local.yaml`（`.gitignore` 已有规则，但此文件在规则前就被跟踪，需手动 untrack）。

## Code（关键片段）

无源码改动。核心是上面的 `filter-branch` 命令。取舍见 `design.md` §2.1：`filter-branch` 官方已不推荐，但本仓库 8 个 commit、无远程、目标文件单一，够用且免安装。

## Test（验证）

```bash
# 1. 全历史是否还有该文件（无输出 = 干净）
git log --all --oneline -- config/config.local.yaml

# 2. 全历史是否还有完整 key
git grep -I "sk-0218" $(git rev-list --all)
```

- 验证 1：**无输出** ✅ 全历史已无 `config.local.yaml`。
- 验证 2：仅剩 `docs/` 内两处**截断引用**（`sk-0218...`，说明性文字，非完整 key）✅。

## Review（复盘）

- ✅ 达成止血：历史无文件、无完整 key；本地配置与备份都在，程序可跑。
- ⚠️ **残留说明性引用**：规划文档与 design.md 保留 `sk-0218...` 截断前缀，用于标记「哪个 key 被吊销」。截断不构成泄露，保留。
- ⚠️ **filter-branch 局限**：无远程仓库，故无需 force-push；若将来推远程，需确认协作者重新 clone（历史已变）。
- 📌 **遗留动作（用户侧）**：在 DeepSeek 控制台吊销 `sk-0218...` 并换新 key —— 代码侧无法代劳，务必确认已完成。
