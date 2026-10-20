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
- 旧版网页前端（请求里没有 `tokens` 字段）返回“页面版本过旧，请刷新页面后重试”。
- token 只能查看，不能取消/改约；写操作仍只认小程序 openid。

## 二、迁移

| 迁移 | 内容 | 说明 |
| --- | --- | --- |
| `0023_meditation_slot_times_20261020` | AlterField choices | 仅 choices 快照，无表结构变更 |
| `0024_med_reservation_query_token_hash` | AddField | 新增可空 64 字符哈希列 |

⚠️ **部署脚本不会自动跑 `migrate`。**
⚠️ `0024` 是新增列；如果先上线代码、后跑迁移，`submit` / `mpl/list` 会短暂报
`no such column: web_med_reservation.query_token_hash`。**请先应用迁移再合并。**

## 三、管理员代办

### 合并前

1. **备份生产数据库**
   ```bash
   cd <平台目录>
   cp db.sqlite3 db.sqlite3.bak_20261020
   ```

2. **删除测试预约单**（时段改版的测试数据；后台按 uid 核对）
   - 后台：`https://gzpt.smupa.top/admin/011215/web/medreservation/`
   - 删除后确认：
     ```bash
     <项目 python> manage.py shell -c "from web import models; print(models.Med_Reservation.objects.count())"
     ```
     期望 `0`，或只剩明确要保留的历史单。

3. **检查生产 `gzpt/local_settings.py`**
   - `MEDITATION_SLOT_REPAIR_CUTOFF` 置空（或过去的确认时间），**不能是未来时间**
   - 如配置了 `MEDITATION_NOTICE_HTML`，同步改成新时间或删除覆盖

4. **先应用迁移（关键）**
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

5. **确认前端已先更新**
   - 静态页必须先部署带 `supports_query_token` / `tokens` 的版本（`?v=20261020`）。
   - 如果旧页面还在用：提交会被拒绝（提示刷新），查询会提示刷新；**不要在前端更新前合并**。

6. **再合并本 PR**，看部署日志：
   ```bash
   tail -f /www/wwwlogs/deploy-smupa_gzpt.log
   ```

### 合并后

7. 如果第 4 步没有预跑迁移，立即补跑：
   ```bash
   <项目 python> manage.py migrate web
   ```

8. 不变量检查：
   ```bash
   <项目 python> manage.py verify_meditation_slots
   ```

9. 线上抽查：
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
