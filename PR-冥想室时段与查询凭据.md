# PR：冥想室最终时段 + 我的预约查询凭据

分支：`feat/meditation-query-token`
提交：

- `891341e` 时段表更新为 2026-10-20 定稿时间
- `6454eda` 新增 `query_token_hash` 字段（仅 schema + 迁移 0024）
- `a4dad2a` 我的预约改为凭查询凭据查看

## 一、本次包含什么

### 1. 运营时段最终调整

工作日仍 7 轮、每轮 40 分钟、轮间 10 分钟，时段 ID 0–6 不变：

| ID | 调整前 | 调整后 |
| --- | --- | --- |
| 0 | 09:10–09:50 | **09:00–09:40** |
| 1 | 10:00–10:40 | **09:50–10:30** |
| 2 | 10:50–11:30 | **10:40–11:20** |
| 3 | 13:10–13:50 | **13:40–14:20** |
| 4 | 14:00–14:40 | **14:30–15:10** |
| 5 | 14:50–15:30 | **15:20–16:00** |
| 6 | 15:40–16:20 | **16:10–16:50** |

- 上午 09:00–11:20；下午 13:40–17:00（16:50 最后一轮结束，16:50–17:00 清场）。
- 前端从 `/layout/`、`/slots/` 动态取时间，不需要改前端。

### 2. 我的预约改为查询凭据

- 提交成功返回一次性 `query_token`（43 字符），数据库只存 SHA-256 哈希。
- `mpl/list` 只返回 openid 或 token 命中的记录；只凭手机号查不到。
- 历史无凭据单只返回日期/时段/状态的最小摘要（`res_date >= 今天`），过期自动不再返回。
  这是**业务方确认保留**的兼容兜底；不要再增加字段（姓名/座位/签到/单号一律不给）。
- 旧版网页前端（请求里没有 `tokens` 字段）返回“页面版本过旧，请刷新页面后重试”。
- token 只能查看，不能取消/改约；写操作仍只认小程序 openid。
- 打印预约单：从详情页点“打印预约单”进入时自动唤起浏览器打印，手动按钮保留。

## 二、迁移

| 迁移 | 内容 | 说明 |
| --- | --- | --- |
| `0023_meditation_slot_times_20261020` | AlterField choices | 仅 choices 快照，无表结构变更 |
| `0024_med_reservation_query_token_hash` | AddField | 新增可空 64 字符哈希列 |

⚠️ **部署脚本不会自动跑 `migrate`。**
⚠️ `0024` 是新增列；如果先上线代码、后跑迁移，`submit` / `mpl/list` 会短暂报
`no such column: web_med_reservation.query_token_hash`。**请先应用迁移再合并。**

## 三、管理员代办

> **日常只看 `管理员代办-极简版.md` 的 6 步即可。**
> 下面是详细说明，供排障/自查使用；预检命令是可选工具，不是必跑项。

### 合并前

0. **复制预检命令（不用先合并代码）**
   ```bash
   cd <平台目录>
   git fetch origin
   git show origin/feat/meditation-query-token:web/management/commands/meditation_preflight.py \
     > web/management/commands/meditation_preflight.py
   ```

1. **备份生产数据库**
   ```bash
   cd <平台目录>
   cp db.sqlite3 db.sqlite3.bak_20261020
   ```

2. **跑预检（默认只读）**
   ```bash
   <项目 python> manage.py meditation_preflight
   ```
   会检查：备份、`cutoff`/`notice`/CORS、0023/0024、`query_token_hash` 列、
   `web_med_slotmigration` 表、全部预约单、前端 `?v=20261020`。
   迁移还没跑时 0023/0024 显示 FAIL 是预期的；先看预约单和配置。

3. **先应用迁移（关键）**
   ```bash
   cd <平台目录>
   git fetch origin
   git show origin/feat/meditation-query-token:web/migrations/0023_meditation_slot_times_20261020.py \
     > web/migrations/0023_meditation_slot_times_20261020.py
   git show origin/feat/meditation-query-token:web/migrations/0024_med_reservation_query_token_hash.py \
     > web/migrations/0024_med_reservation_query_token_hash.py
   <项目 python> manage.py migrate web
   rm web/migrations/0023_meditation_slot_times_20261020.py \
      web/migrations/0024_med_reservation_query_token_hash.py
   ```
   期望看到 `Applying web.0023... OK`、`Applying web.0024... OK`。
   > `<项目 python>` 用宝塔 Python 项目管理器里该项目实际使用的解释器，不要用仓库里的 `smupa_gzpt_venv/`。

4. **再跑一次预检，确认迁移/列都 OK**
   ```bash
   <项目 python> manage.py meditation_preflight
   ```
   期望 0 项 FAIL；前端检查可能 WARN，确认 v2 已上线即可。

5. **删除测试单（先 dry-run，再 --apply）**
   ```bash
   <项目 python> manage.py meditation_preflight --delete-uids 1,2,3
   ```
   确认名单无误后：
   ```bash
   <项目 python> manage.py meditation_preflight --delete-uids 1,2,3 --apply \
     --output /tmp/meditation_deleted.csv
   ```
   - 会级联删除表单/操作/分享/迁移记录。
   - 此时迁移已 OK，命令应正常退出；如果预检还有 FAIL，先处理再删。
   - 不想用命令也可以继续在后台按 uid 删。

6. **确认前端已先更新**
   - 静态页必须先部署带 `supports_query_token` / `tokens` 的版本（`?v=20261020`）。
   - 如果旧页面还在用：提交会被拒绝（提示刷新），查询会提示刷新；**不要在前端更新前合并**。

   Ubuntu 侧部署（`learning-assistant` 仓库，`feat/meditation-booking` @ `1d68fd2`）：

   ```bash
   cd /path/to/learning-assistant
   git fetch origin
   git checkout feat/meditation-booking
   git pull
   sudo Web/tools/sync-meditation.sh v2
   ```

   - `v2` = 带查询凭据的新前端；`v1` = 旧版，保留用于回滚。
   - `sync-meditation.sh` 会把版本同步到 `/var/www/meditation/` 并把 `current` 指向 v2。
   - **不需要** reload nginx、不需要重启学习助手容器、不需要数据库迁移。
   - nginx 对 `/meditation/` 已经是 `no-cache`，不需要改缓存配置。

   回滚前端：

   ```bash
   sudo Web/tools/sync-meditation.sh v1
   ```

   ⚠️ `v1` 不支持 `query_token` / `tokens`；**回滚前端必须同时回滚平台后端 PR**，
   否则旧页面的提交会被新后端的 `supports_query_token` 闸门拒绝。

7. **再合并本 PR**，看部署日志：
   ```bash
   tail -f /www/wwwlogs/deploy-smupa_gzpt.log
   ```

### 合并后

8. 如果第 4 步没有预跑迁移，立即补跑：
   ```bash
   <项目 python> manage.py migrate web
   ```

9. 不变量检查：
   ```bash
   <项目 python> manage.py verify_meditation_slots
   ```

10. 线上抽查：
   ```bash
   curl -s https://gzpt.smupa.top/meditation/api/layout/
   curl -s https://gzpt.smupa.top/meditation/api/notice/
   curl -s "https://gzpt.smupa.top/meditation/api/slots/?date=2026-10-21"
   ```
   - `/layout/`：首档 `09:00-09:40`，末档 `16:10-16:50`
   - `/notice/`：含 `09:00`、`11:20`、`13:40`、`16:50`、`17:00`
   - `/slots/`：7 档新时间，`taken` 为空

10. 查询凭据抽查（用一张临时单，事后作废/删除）：
    - `submit` 响应含 43 字符 `query_token`
    - 只带手机号 `mpl/list` → 提示“请刷新页面”或空列表
    - 带 token → 能看到单号/座位，但没有姓名、没有 `can_cancel`
    - 带 token 取消 → 仍被拒

### 禁止

- ❌ 不要运行 `repair_meditation_slots`（那是 11 档 → 7 档的旧迁移命令）
- ❌ 不要把 `MEDITATION_SLOT_REPAIR_CUTOFF` 设成未来时间
- ❌ 不要在前端更新前合并

## 四、回滚

- 代码：Gitee revert 合并提交，或重新部署上一个 `master`。
- 迁移：`0023` 是 choices-only；`0024` 只是加了一个可空列，回滚代码不需要删列。
- 数据：用 `db.sqlite3.bak_20261020` 覆盖。
- 前端：回退到上一个 `meditation_versions` 版本指针。

## 五、验证（本地已跑）

`smupa_local_env`：

```
env / migrate / unit / integration / contract / rehearsal / browser / faults
全部 PASS
```

新增 `web/test_meditation_query_token.py` 11 条，覆盖：token 只存哈希、
手机号单独查不到、token 只读、openid 完整视图、历史最小摘要、续约复制哈希、
表单/后台不暴露哈希、旧前端刷新提示。
