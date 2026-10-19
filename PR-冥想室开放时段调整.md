# PR：冥想室开放时段调整为工作日 7 档（v3，已 rebase !5）

**分支**：`feat/meditation-open-hours-v3`
**目标**：`master`（已包含 !5 `2273270`）
**HEAD**：`20db6ac`
**创建 PR**：<https://gitee.com/xing_young/smupa_gzpt/pull/new/xing_young:feat/meditation-open-hours-v3...xing_young:master>
**前情**：原 PR !6、!7 评审未通过。本 PR 是重新提交的新 PR：
按 !6 意见重做、rebase 到 !5，并修复 !7 BUG 实测清单的 4 个代码问题，
同时把迁移状态从 comment 标记改成 `Med_SlotMigration` 表 + `get_slot_state()` 单一事实源。
**旧 PR !7（v2 分支）已被本 PR 取代，请关闭。**

## 本版针对 !7 BUG 清单的修复

| BUG | 修复 |
| --- | --- |
| 长 comment 截断吃掉 `【时段迁移】`，重复 apply 把已修复单作废 | 标记改为写在 comment **最前面**，截断只影响旧备注；补“长 comment + 重复 apply”回归测试 |
| 修复后旧 1/4/5 的未验证单仍然过不了 `reg` | `_is_pre_deploy_booking` 识别 comment 里的“已改编号”标记；修复后不再按旧单拦截；补 reg 回归测试 |
| 旧 0/2/3/6 在列表/打印/详情仍显示新时间 | `slot_display` 结合修复标记与部署时间：未改编号的旧单显示旧时段 + “已停用”；已改编号的显示新时段；补显示测试 |
| 修复后详情页“原时段”标签张冠李戴（旧 4→新 3 显示成 11:05–11:45） | 从修复标记中解析原始旧时段（`旧时段 4（13:10-13:50）`）；修复后的单不再显示旧时段下拉；补详情 context 测试 |

`MEDITATION_SLOT_REPAIR_CUTOFF` 现在**必须带时分**（`YYYY-MM-DD HH:MM`）：
只写日期会被忽略，`repair_meditation_slots --cutoff` 也会直接报错。

### 结构性修复：迁移状态表 + 单一事实源

新增 `Med_SlotMigration` 表（OneToOne，`reservation_uid` 唯一）：

| 字段 | 用途 |
| --- | --- |
| `old_slot` / `new_slot` | 原始旧编号 / 新编号 |
| `action` | `remap` / `void` / `mark` / `conflict` |
| `note` / `migrated_at` | 说明与处理时间 |

所有“是否旧单 / 是否已修复 / 该显示什么 / 要不要重选”的判断统一走
`web/meditation_slot_state.py:get_slot_state()`，不再从 `comment` 或
`create_datetime` 推断。这样：

- 长 comment 截断不会影响状态；
- 修复后的单 `reg`/受理/改约不会被再次当成旧单；
- 旧 0/2/3/6 与修复后的标签都有原始旧时段可查；
- 迁移记录唯一约束保证命令幂等。

新增 `python manage.py verify_meditation_slots`：检查有效单是否仍有旧编号、
是否重复占用、迁移记录是否一致、是否仍有需人工重选的单；有问题退出码 1。

---

## 一、必改 1：老预约的时段编号修复

### 1.1 问题

数据库存的是**时段编号**，不是时间。改版后：

| 旧编号 | 旧时间 | 新编号 | 新时间 | 处理 |
| --- | --- | --- | --- | --- |
| 1 | 9:10-9:50 | 0 | 9:10-9:50 | 自动改编号 |
| 4 | 13:10-13:50 | 3 | 13:10-13:50 | 自动改编号 |
| 5 | 14:00-14:40 | 4 | 14:00-14:40 | 自动改编号 |
| 0/2/3/6/7/8/9/10 | 无对应 | — | — | 作废或标记，输出名单 |

不修会：旧单显示错时间；旧 1/4/5 与新 0/3/4 时间相同但编号不同，占用判断绕开，可能同一座位同一时间约两次。

### 1.2 修复命令

已新增 management command：

```bash
# 第一步：dry-run（只打印，不写库）
python manage.py repair_meditation_slots --dry-run \
    --cutoff "2026-10-20 18:00"
```

`--cutoff` **必须填部署/合并上线时间**：命令只处理该时间之前创建的单，避免把上线后产生的新编号预约误当旧单。
如果已在 `local_settings.py` 配置 `MEDITATION_SLOT_REPAIR_CUTOFF`，可省略 `--cutoff`，命令会自动取该值。

确认名单无误后再执行：

```bash
python manage.py repair_meditation_slots --apply \
    --cutoff "2026-10-20 18:00" \
    --output /www/wwwroot/meditation_slot_migration.csv
```

`--output` 会写一份 CSV（UTF-8 BOM，Excel 可直接打开），用于通知同学 / 人工改约。

### 1.3 `--dry-run` 预期输出（示例）

```text
cutoff = 2026-10-20 18:00:00（只处理该时间之前创建的单）
模式 = DRY RUN（不写库）
UID    姓名        手机号          日期          旧档  旧时段       状态  动作    新档  说明
1001   张三        13900001001    2026-10-21    1     9:10-9:50    1     remap   0     旧 1 -> 新 0
1002   李四        13900001002    2026-10-21    4     13:10-13:50  0     remap   3     旧 4 -> 新 3
1003   王五        13900001003    2026-10-21    5     14:00-14:40  5     remap   4     旧 5 -> 新 4
1004   赵六        13900001004    2026-10-21    8     18:00-18:40  1     void          旧时段无对应，整单作废
1005   钱七        13900001005    2026-10-20    9     18:50-19:30  2     mark          旧时段无对应，历史单标记保留
合计：mark 1，remap 3，void 1
[DRY RUN] 未写库。确认名单无误后加 --apply 再执行一次。
```

动作含义：

| 动作 | 含义 |
| --- | --- |
| `remap` | 自动改编号，并同步 `Med_Form_Data.res_datetime` |
| `void` | 旧编号无对应、当前仍有效（状态 0/1/4/5）→ 整单作废 |
| `mark` | 旧编号无对应、历史已完成/已作废 → 只写标记，保留状态 |
| `conflict` | 目标新时段同座位已被别的有效单占用 → **不自动改编号**，留给人工 |
| `skip` | 已处理过（带 `【时段迁移】` 标记）、不是旧编号、或无状态记录 |

### 1.4 幂等与回滚

- **幂等**：以 `Med_SlotMigration` 唯一记录为准；重复执行会跳过，不会二次改编号或重复作废。
  上一版用 `【时段迁移】` comment 标记处理过的单，命令会自动补迁移记录（`backfill`），不改数据。
- **回滚方式**：
  1. 执行 `--apply` 前先备份数据库（宝塔/部署脚本的备份即可）；
  2. 保留 `--output` 生成的 CSV 作为变更清单；
  3. 如需回滚，直接恢复备份数据库。
- `0021_meditation_slot_schedule` **只改 choices，不改数据**，不能替代本命令。

### 1.5 脚本执行前的代码拦截

- 旧编号（7–10）单：`reg`（通过验证）、`reservation`（受理）、`change`（改约）都会直接返回
  “该预约使用旧时段（已停用），请先改约到新时段”，不会写库。
- 旧 0/2/3/6 的编号仍在、单看 ID 无法识别，因此增加配置项
  `MEDITATION_SLOT_REPAIR_CUTOFF`（部署时间）：
  该时间之前创建的单，必须由值班员显式重选 0–6 中的一档（前端 `slot_changed=1`）才允许受理/改约，
  否则一律报“请先改约到新时段”。这样部署到脚本执行之间的空窗也不会把老单改错。
- 旧编号在列表/详情/打印/分享页显示为
  `15:55-16:35（旧时段，已停用）`，不再显示光秃秃的 `8/9/10`。

---

## 二、必改 2：旧单不再被静默改成 0 号档

根因：详情页的 `<select>` 只有新 0–6，旧单（7–10）没有匹配项，浏览器默认提交第一个 option（0）。

修复：

1. **模板**：旧编号单的“受理 / 改约”下拉顶部新增灰色选项
   `原时段（已停用）：15:55-16:35`（`value=""`、默认选中），强制值班员重选。
2. **后端**：
   - 提交空值/旧编号 → 返回“请先改约到新时段”；
   - 旧缓存页面仍默认提交 0 时，只有下拉真的被操作过（`slot_changed=1`）才允许写 0；
   - 事务内复审座位，避免并发撞座。
3. **旧编号单**的 `reg` 也直接拦截，避免先验证后卡住。

---

## 三、评审建议一并修的 4 个小 bug

| # | 问题 | 修复 |
| --- | --- | --- |
| 1 | `reg` 把“早于今天”也带进来，过期未验证单只能废弃 | `reg` 跳过过去日期检查；开放日/时段/座位仍然校验；过期的工作日单可正常通过验证 |
| 2 | `MEDITATION_CLOSED_DATES` 配成单个 `date`/`int` 时 `for` 报 TypeError，多个接口 500 | 非 list/tuple/set 统一包成单元素列表；非法项记 warning 不抛异常 |
| 3 | `meditation_date_error` 对非法入参返回“可约” | `None`/非日期 → “日期不合法”；坏字符串 → “日期格式不合法（应为 YYYY-MM-DD）” |
| 4 | 全部闭馆时 `upcoming_open_dates` 返回空列表，选座页报错 | 选座页空列表时显示“暂无开放日”，不再请求接口 |

---

## 四、迁移

包含两个迁移：

| 迁移 | 内容 |
| --- | --- |
| `0021_meditation_slot_schedule` | 仅 `Med_Reservation.slot` 的 choices `AlterField`，不改列类型、不改数据 |
| `0022_med_slot_migration` | 新建 `Med_SlotMigration` 迁移记录表（OneToOne） |

部署脚本**不会**自动跑 migrate。合并后请**立即**执行：

```bash
python manage.py migrate web
```

`0022` 只是新建表。代码对“表尚未迁移”做了回退：`get_slot_state()` 会捕获
`OperationalError` 并按“无迁移记录”处理，列表/详情页在 deploy 完成到 migrate
之间的短窗口内**不会 500**；但 `repair_meditation_slots` 和
`verify_meditation_slots` 必须先完成 migrate 才能运行。`0021` 只是 choices 快照。

---

## 五、配置（可直接粘贴）

`gzpt/local_settings.py`：

```python
# 法定节假日/临时闭馆日期；不配 = 节假日照常放号
# 请替换成学校实际停开日期，这里只是格式示例
MEDITATION_CLOSED_DATES = [
    '2027-01-01',  # 元旦
    '2027-02-06',  # 示例：寒假开始
]
```

> 正式仓库**不读取 `.env`**，必须写在 `gzpt/local_settings.py`。

若生产已配置旧的 `MEDITATION_NOTICE_HTML`，新默认须知不会生效，请同步更新或删除该覆盖项。

### 修复窗口截止时间（建议配）

`gzpt/local_settings.py`：

```python
# 部署时间：该时间之前创建的单，在值班员受理/改约时必须显式重选时段
# 必须带时分；只写日期会漏掉部署当天早些时候的旧单
MEDITATION_SLOT_REPAIR_CUTOFF = '2026-10-20 18:00'
```

- 修复命令的 `--cutoff` 用同一个时间；
- 修复完成后可以保留该配置：上线后新单的 `create_datetime` 晚于它，不受影响；
- 不配也能拦住旧 7–10，但拦不住旧 0/2/3/6 的“编号相同、语义已变”。

---

## 六、验证

### 6.1 服务器上可直接跑（Django TestCase）

```bash
python manage.py test web.test_meditation_slots
```

共 36 条，覆盖：

- 旧编号显示（7–10 显示“旧时段，已停用”）
- 旧单 `reg`/受理不会被静默写成 0
- `MEDITATION_CLOSED_DATES` 配成单个 `date`/`int`/字符串不 500
- 周末 / 闭馆日 / 跨年 / 全部闭馆空列表
- 修复命令 dry-run、apply、幂等、冲突不自动改号、cutoff 之后的新单不动
- 长 comment 下重复 apply 不丢标记、不把已修复单作废
- 修复后旧 1/4/5 的 reg 成功
- 旧 0/2/3/6 的列表/详情显示旧时段；修复后详情页“原时段”标签取原旧时段
- `get_slot_state` 对 remap/void/mark/conflict 四种记录的状态
- `verify_meditation_slots`：干净库通过；重复座位/旧编号有效单退出码 1
- 上一版 comment 标记自动回填迁移记录

### 6.2 本地全量回归（已跑）

| 套件 | 结果 |
| --- | --- |
| `manage.py check` | 无问题 |
| `makemigrations --check` | No changes detected |
| `verify1` / `verify2` / `verify4` | 49 / 82 / 77 通过 |
| `verify_e2e` | 217 通过 |
| `mp_simulate.js` / `web_simulate.js` | 54 / 46 通过 |
| `_verify_owns.py` | 26 通过 |
| `_audit_roles.py` | 主席 / 主席助理全流程通过 |

### 6.3 人工验证（最多 3 条）

1. **旧单不再默认改 0**：打开一张旧时段预约详情 → “受理”弹窗的时段下拉第一项显示
   “原时段（已停用）：…”；不选新时段直接点“确认受理” → 时段下方出现
   “请先改约到新时段”，单号时段保持不变。
2. **旧编号显示**：打开预约列表/详情 → 旧 8 号档显示
   “18:00-18:40（旧时段，已停用）”，不再只显示“8”。
3. **开放日**：进入“冥想室选座总览” → 日期下拉只有工作日；选一个周末
   直接调 `/meditation/api/slots/?date=周六` → 返回 `status:false` 和
   “冥想室仅工作日开放（周一至周五）”。

---

## 七、合并顺序与风险

1. 本 PR 已 rebase 到 `!5` 合并后的 `master`（`2273270`）。
2. 合并前在 `gzpt/local_settings.py` 配 `MEDITATION_SLOT_REPAIR_CUTOFF` = 本次部署时间。
3. 合并/部署完成后**立即** `python manage.py migrate web`（代码对缺表有回退，
   窗口内页面不会 500；但修复/校验命令必须先 migrate）。
4. 执行修复命令；命令的 `--cutoff` 填同一个部署时间，最后跑
   `python manage.py verify_meditation_slots` 确认 `OK`。
5. 修复命令先 `--dry-run` 给管理员/业务方看名单，确认后再 `--apply`。
6. 若 `--dry-run` 名单里出现上线后创建的、使用新编号的正常单 → 说明 cutoff 填晚了，
   请改用精确的部署时间重跑，不要直接 `--apply`。
7. 修复命令不会自动改 `conflict` 单；这些单需要人工改约或作废。
