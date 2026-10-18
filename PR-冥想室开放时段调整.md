# PR：冥想室开放时段调整为工作日 7 档

**分支**：`feat/meditation-open-hours`
**目标**：`master`
**创建 PR**：<https://gitee.com/xing_young/smupa_gzpt/pull/new/xing_young:feat/meditation-open-hours...xing_young:master>

---

## Summary

- 按督导定稿，把冥想室时段由 11 档改为**工作日 7 档**（每档 40 分钟）：
  - 上午：09:10–09:50、10:00–10:40、10:50–11:30
  - 下午：13:10–13:50、14:00–14:40、14:50–15:30、15:40–16:20
- 周一至周五开放；周末与 `MEDITATION_CLOSED_DATES` 中的日期不开放。
- `/meditation/api/layout/` 新增契约字段：
  - `open_weekdays`：`[0,1,2,3,4]`（Python `weekday()`，周一=0）
  - `open_weekdays_iso`：`[1,2,3,4,5]`（与 JS `Date.getDay()` 的周一至周五一致，推荐前端置灰用这个）
  - `closed_dates`：`["YYYY-MM-DD", ...]`
- `/meditation/api/slots/?date=` 对非开放日返回 `status:false` + `error.date`，不返回 `per_slot`。
- 平台代录、通过验证（reg）、受理、改约、续约全部统一校验开放日。
- 默认《须知》文案更新为定稿排期。

## Migration

包含迁移：`web/migrations/0021_meditation_slot_schedule.py`
（仅 `Med_Reservation.slot` 的 choices `AlterField`，不改列类型、不是数据库约束。）

部署脚本**不会**自动跑 migrate。合并后请管理员执行：

```bash
python manage.py migrate web
```

## 合并前必须复核线上数据

`slot` 是直接落库的整数，id 0–6 的语义已整体替换。合并前执行：

```sql
SELECT COUNT(*) FROM web_med_reservation;
SELECT slot, COUNT(*) FROM web_med_reservation GROUP BY slot ORDER BY slot;
```

**必须为 0**。若有历史/未来单，暂停合并并先处理数据（旧 id 7–10 在新表中不存在）。
委托方已口头确认线上无真实预约数据，但仍需管理员复核一次。

## Configuration

本仓库**不读取 `.env`**，以下配置写 `gzpt/local_settings.py`：

```python
# 法定节假日等临时闭馆日期（不配则节假日仍会放号）
MEDITATION_CLOSED_DATES = ['2026-10-01', '2026-10-02']
```

若生产已配置旧的 `MEDITATION_NOTICE_HTML`，新默认须知不会生效，请同步更新或删除该覆盖项。

## 前端 / 小程序

- 时段表、须知文案均从接口自动跟随，无需硬编码。
- 日期置灰请用 `open_weekdays_iso` + `closed_dates`（不要用 `open_weekdays` 直接喂 JS `getDay()`，两者 weekday 起点不同）。
- 小程序若缓存 `/layout/`，合并后需刷新缓存；旧 slot id 7–10 已不存在。

## Verification

在**包含 `fix/meditation-idor` 的本地分支**上（功能代码相同）全绿：

| 套件 | 结果 |
| --- | --- |
| `manage.py check` | 无问题 |
| `makemigrations --check` | No changes detected |
| `verify1` | 49 通过 |
| `verify2` | 82 通过（含五条创建路径的周末/闭馆日负例） |
| `verify4` | 77 通过 |
| `verify_e2e` | 217 通过（含新增 [18] 开放日校验） |
| `mp_simulate.js` | 54 通过 |
| `web_simulate.js` | 46 通过 |
| `_verify_owns.py` | 26 通过 |
| `_audit_roles.py` | 主席 / 主席助理全流程通过 |

本 PR 分支从 `origin/master` 切出，因此 `verify4` 与 `verify_e2e` 中**依赖越权修复**
的断言会失败（master 尚未合入 `fix/meditation-idor`）；`verify1` / `verify2` 全绿。
建议先合并越权修复，再合并本 PR。

## 与上级初稿的差异

上级初稿写 09:00–11:00 / 14:00–17:00；学习助手侧交接文档（2026-10-14 定稿）改为
09:10–11:30 / 13:10–17:00，并注明“以本清单为准”。本 PR 按定稿实现。若需改回初稿，请先确认。
