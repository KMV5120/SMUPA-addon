# PR：冥想室归属判断只认 openid（堵死手机号越权）

**分支**：`fix/meditation-idor`（已推送，HEAD `e9a63ef`）
**目标**：`master`
**改动**：1 个文件，+54 −25（`web/views/meditation_api.py`）

---

## 问题

`_owns()` 原有一条“对外网页凭手机号认领”的分支：

```python
if mobile_phone and res_obj.mobile_phone == str(mobile_phone).strip():
    return True
```

手机号是半公开信息（同学之间互相知道，且可枚举）。任何匿名请求只要知道对方手机号，
就能读取（含姓名/手机号/座位/签到时间）、改约、取消他人的预约单。
已用 `_repro_idor.py` 实测复现。

## 修复

- `_owns()` **只认微信小程序 openid**；无 openid 一律拒绝。
- `my_list` 仍保留“按手机号查询”这一产品设计，但字段按归属分级：
  - 本人：完整字段（含 `can_cancel` / `cancel_reason`）
  - 非本人：不返回姓名，手机号只留后 4 位，不下发 `can_cancel`
- 对外网页侧不再提供自助改约/取消；需要时联系值班员在平台端操作
  （平台端本就有改约/废弃/清空）。
- 前端侧已先移除网页改约/取消入口（learning-assistant `feat/meditation-booking` @ `7f27088`），
  但服务端封堵才算修复。

## 无迁移

纯视图逻辑改动，不涉及模型/表结构。

## 验证

在 `fix/meditation-idor` 分支上：

| 套件 | 结果 |
| --- | --- |
| `_verify_owns.py` | 26 通过 |
| `_repro_idor.py` | 取消/改约攻击均被拒，状态与座位未变 |
| `verify4` | 77 通过（含匿名取消/改约负例） |
| `verify_e2e` | 217 通过 |

## 已知残留（不在本 PR 范围）

匿名仍可凭手机号看到他人的**日期/时段/座位/状态**（姓名与手机号已脱敏）。
这是“输入手机号查我的预约”产品设计的固有暴露；彻底关闭需改为“凭单号查询”或加短信验证码，
属于另开需求。

## 合并顺序

建议**先合并本 PR**，再合并 `feat/meditation-open-hours`。
后者从 `origin/master` 切出，其 `verify4` / `verify_e2e` 中依赖本次越权修复的断言，
在 master 未合入本 PR 前会失败；这不是功能代码的问题。
