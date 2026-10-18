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

## 上线待办（按角色 / 端）

### A. 管理员 · 平台后端（Gitee + 服务器）

| 时机 | 事项 | 不做的后果 |
| --- | --- | --- |
| 合并前 | 先合并 `fix/meditation-idor`（`e9a63ef`） | 手机号越权读/改/取消仍在 |
| 合并前 | 执行线上数据复核 SQL（见下节） | 旧 slot id 语义错乱 |
| 合并前 | 检查 `gzpt/local_settings.py` 的 `MEDITATION_CLOSED_DATES` / `MEDITATION_NOTICE_HTML` / `MEDITATION_CORS_ORIGINS` | 节假日放号 / 新须知不生效 / 提交跨域失败 |
| 合并 | 合并本 PR `feat/meditation-open-hours`（`c921041`） | 新时段不上线 |
| 合并后 | `python manage.py migrate web` | `0021` 未应用 |
| 合并后 | 验证 `/meditation/api/layout/` 返回 7 档 + `open_weekdays*` + `closed_dates`；`/slots/?date=周末` 返回 `status:false` | 线上仍是旧契约 |

### B. 学习助手 · 对外网页（Ubuntu 侧）

| 时机 | 事项 | 不做的后果 |
| --- | --- | --- |
| 平台上线后 | 日期选择器用 `open_weekdays_iso` + `closed_dates` 置灰 | 同学能选周末，提交时才报错 |
| 平台上线后 | 确认线上页面版本已切到最新静态版 | 同学看到旧页面 |
| 持续 | 时段表 / 须知继续从 `/layout/`、`/notice/` 取，不硬编码 | 下次改排期还得改前端 |
| 可选 | `/slots/` 返回 `status:false` 时展示 `msg`，不要静默 | 同学不知道为何选不了 |

### C. 微信小程序端

| 时机 | 事项 | 不做的后果 |
| --- | --- | --- |
| 平台上线后 | 刷新 `/layout/` 缓存 | 仍显示旧 11 档，提交 id 7–10 被拒 |
| 平台上线后 | slot id 只接受 0–6；处理 `/slots/` 非开放日错误 | 选到旧档位/周末后提交失败 |
| 平台上线后 | 日期置灰用 `open_weekdays_iso` + `closed_dates` | 同 B 侧 |

### D. 业务方 / 督导

| 时机 | 事项 | 不做的后果 |
| --- | --- | --- |
| 合并前 | 确认最终时段口径：定稿 09:10–11:30 / 13:10–17:00，还是上级初稿 09:00–11:00 / 14:00–17:00 | 文档与系统口径冲突 |
| 合并前 | 提供法定节假日停开日期清单 | 节假日仍会放号 |
| 上线后 | 定稿《值班员工作手册》（开放前设备调试、闭室后关机整理、两场闭室时间） | 值班员无统一操作口径 |

### E. 值班员 · 线下操作

| 时机 | 事项 |
| --- | --- |
| 开放前 | 完成全部设备通电调试 |
| 闭室后 | 设备检查、关机、整理房间、填写使用记录表 |
| 11:30 / 17:00 | 所有使用者结束冥想、退场签退 |

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
