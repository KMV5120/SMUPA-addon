# PR：冥想室运营时段最终调整（2026-10-20 定稿）

## 1. 变更内容

工作日仍为 7 轮、每轮 40 分钟、轮间 10 分钟缓冲，只调整时刻；时段 ID 0–6 不变。

| 轮次 | ID | 调整前 | 调整后 |
| --- | --- | --- | --- |
| 上午第 1 轮 | 0 | 09:10–09:50 | **09:00–09:40** |
| 上午第 2 轮 | 1 | 10:00–10:40 | **09:50–10:30** |
| 上午第 3 轮 | 2 | 10:50–11:30 | **10:40–11:20** |
| 下午第 4 轮 | 3 | 13:10–13:50 | **13:40–14:20** |
| 下午第 5 轮 | 4 | 14:00–14:40 | **14:30–15:10** |
| 下午第 6 轮 | 5 | 14:50–15:30 | **15:20–16:00** |
| 下午第 7 轮 | 6 | 15:40–16:20 | **16:10–16:50** |

- 上午开放 09:00–11:20，11:20 闭室。
- 下午开放 13:40–17:00；16:50 最后一轮结束，16:50–17:00 清场收尾，17:00 闭室。
- 前端从 `/layout/`、`/slots/` 动态取时段，无需改前端。

## 2. 改动文件

- `web/meditation_constants.py`：7 档时间、起止时间、注释
- `web/views/meditation_api.py`：须知文案增加清场收尾说明、示例时间
- `web/migrations/0023_meditation_slot_times_20261020.py`：`AlterField` choices 快照
- `web/models.py`、`web/templatetags/meditation_tags.py`、`web/management/commands/repair_meditation_slots.py`、`static/css/meditation.css`：注释/示例同步
- `gzpt/settings.py`：修正 `MEDITATION_SLOT_REPAIR_CUTOFF` 的误导说明
- `web/test_meditation_slots.py`：当前时段断言 + 两条守卫测试

## 3. 上线顺序（重要）

1. **先备份生产数据库**。
2. 管理员核对并删除测试预约单（当前线上公开接口只看到 2026-10-22 时段 0 的 2 条占用，以后台实际列表为准）；删除后确认 `Med_Reservation` 为空或只剩明确保留的历史单。
3. 检查生产 `gzpt/local_settings.py`：
   - `MEDITATION_SLOT_REPAIR_CUTOFF` 置空（或设为过去的确认时间），**不能是未来时间**。
   - 若配置了 `MEDITATION_NOTICE_HTML`，同步改成新时间或删除覆盖。
4. 合并 PR（合并即自动部署）。
5. 管理员手动执行 `python manage.py migrate web` —— **部署脚本不会自动跑 migrate**。
6. 执行 `python manage.py verify_meditation_slots`。
7. 线上抽查 `/meditation/api/layout/`、`/meditation/api/notice/`、`/meditation/api/slots/?date=...`。

## 4. 注意事项

- **不要运行 `repair_meditation_slots`**：它是 2026-10-19 那批 11 档 → 7 档的迁移命令；本次只运行 `verify_meditation_slots`。
- `Med_Form_Data.res_datetime` 是反规范化旧文本。测试单删干净后无影响；若仍有历史单，列表显示新时间而详情/问卷/邮件可能仍显示旧文本。
- 删除全部预约后，下一单 uid 会从 1 重新开始；测试数据无影响。
- 迁移 `0023` 只改 choices，SQLite 无实际表结构变更，不丢数据。
