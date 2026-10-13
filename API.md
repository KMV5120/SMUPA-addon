# 冥想室预约 · 接口规格

**给开发方（你的平台侧）** —— 同学预约页面调用本平台接口的完整说明。

> 同学页面托管在你自己的域名上，通过这 8 个接口把数据发到 SMUPA 平台处理。

---

## ★ 唯一需要配置的东西

你那边只需要填**一个字段**：

```
SMUPA 平台接口地址 = https://<平台域名>/meditation/api
```

- 必须是 **https**
- 结尾**不带**斜杠
- 结尾必须是 `/meditation/api`

其余全部已经就绪，不需要你配置任何东西。

**⚠️ 另外还必须让管理员在 SMUPA 平台的 `.env` 里加上你的域名：**

```ini
MEDITATION_CORS_ORIGINS=https://kmv-learning-assistant.xyz
```

**不加的话，浏览器会拦住请求 —— 页面能打开，但一点提交就失败。**
这是唯一一个「不配就完全不可用」的外部依赖。

> 注意**不要**写成 `https://kmv-learning-assistant.xyz/`（多尾斜杠）
> 或带上路径 `/meditation/`：平台侧是精确字符串匹配，多一个字符就静默失效，
> 且不报任何错。浏览器发的 `Origin` 头只有 `scheme://host`，不含路径。

---

## 约定

| 项 | 说明 |
| --- | --- |
| 请求方法 | 一律 `POST`（`layout` / `notice` / `slots` 也接受 `GET`，便于浏览器直接调试） |
| Content-Type | `application/json` |
| 编码 | UTF-8 |
| 跨域 | 平台已放行你的域名（见上）。**浏览器会自动先发 OPTIONS 预检**，平台已处理，你无需关心 |

### 响应统一格式

```json
{
  "status": true,      // 业务是否成功
  "data":   { },       // 成功时的数据
  "error":  { },       // 失败时的字段级错误：{"seat": "该座位已被预约"}
  "msg":    "提示文案"  // 可直接展示给同学
}
```

- `status=false` 时 `msg` 一定非空，可直接 toast
- `error` 非空表示**字段级**错误，建议红字标在对应输入框旁

---

## 接口一览

| # | 接口 | 用途 | 鉴权 |
| --- | --- | --- | --- |
| 1 | `layout/` | 取时段表 + 17 座坐标 + 选项 | 无 |
| 2 | `notice/` | 取《须知与承诺》正文 | 无 |
| 3 | `slots/` | 查某日各时段占用 | 无 |
| 4 | `submit/` | 提交预约 | 无 |
| 5 | `mpl/list/` | 查我的预约（凭手机号） | 无 |
| 6 | `cancel/` | 取消预约 | 凭手机号 |
| 7 | `reschedule/` | 改约 | 凭手机号 |
| 8 | `wxlogin/` | 微信小程序登录（**现在用不到**） | 无 |

> 只有第 8 个是给将来的小程序预留的，**网页对接完全不需要它**。

---

## 1. `GET layout/` — 时段表与座位图

页面初始化时调一次。

**响应**
```json
{
  "status": true,
  "data": {
    "slots": [
      {"id": 0, "label": "8:20-9:00", "start": "08:20", "end": "09:00"},
      ... 共 11 档，每档 40 分钟
    ],
    "seats": [
      {"no": 1, "x": 5, "y": 17},
      ... 共 17 个，x/y 是百分比坐标
    ],
    "door": {"x": 4, "y": 91},
    "seat_count": 17,
    "max_use_minutes": 40,
    "min_ahead_minutes": 5,
    "reschedule_limit_minutes": 60,
    "notice_min_read_seconds": 5,
    "meditation_room": "410B",
    "checkin_room": "412",
    "choices": {
      "sex":     [[0,"女"],[1,"男"],[2,"其他或不便透露"]],
      "college": [[0,"商船学院"], ...],
      "grade":   [[0,"预科"],[1,"大一"], ...]
    }
  }
}
```

**座位图渲染**（务必照此实现，才能与平台端一致）：

```html
<div class="room"><!-- 容器固定 3:4 比例 -->
  <!-- 每个座位 -->
  <div class="seat" style="left:5%; top:17%;">1</div>
  <!-- 门 -->
  <div class="door" style="left:4%; top:91%;">门</div>
</div>
```
```css
.room { position: relative; width: 340px; height: 452px; }
.seat { position: absolute; border-radius: 50%;
        /* 关键：让圆心（而非左上角）落在坐标点上 */
        transform: translate(-50%, -50%); }
```

> 坐标由服务端下发，**不要在前端硬编码** —— 这样你的座位图与平台端永远一致。

---

## 2. `GET notice/` — 《须知与承诺》

```json
{
  "status": true,
  "data": {
    "title": "冥想室使用须知与承诺",
    "html": "<p>...</p>",
    "min_read_seconds": 5,
    "meditation_room": "410B",
    "checkin_room": "412"
  }
}
```

`html` 是富文本，直接 `innerHTML` 渲染。

**阅读门禁**：页面停留满 `min_read_seconds` 秒后才允许下一步，
并把**实际停留秒数**在提交时作为 `read_seconds` 回传 —— **服务端会再校验一次**，
传小于 5 会被拒。

---

## 3. `GET slots/?date=YYYY-MM-DD` — 某日各时段占用

```json
{
  "status": true,
  "data": {
    "date": "2026-10-19",
    "taken": [[5, 7], [5, 9], [10, 12]],
    "seat_count": 17,
    "per_slot": [
      {"slot": 0, "label": "8:20-9:00", "taken": 0, "full": false},
      ... 共 11 档
    ]
  }
}
```

- 选时段：用 `per_slot` 标「已满 / 剩余 N 位」
- 选座：用 `taken` 里属于当前时段的 `[时段id, 座位号]`，把对应座位置灰

> 有多个日期要展示时，逐日调这个接口（每次 1 个请求，很轻）。

---

## 4. `POST submit/` — 提交预约

**请求**
```json
{
  "name": "张三", "sex": 0, "college": 2, "grade": 2,
  "stu_code": "2023123456", "mobile_phone": "13911112222",
  "email": "zhangsan@example.com",
  "res_date": "2026-10-19", "slot": 5, "seat": 7,
  "note": "希望安静一些",
  "agree": 1, "read_seconds": 8
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | ✓ | 姓名 |
| `mobile_phone` | ✓ | 手机号（服务端用它做**防重复提交**，也是后续改约/取消的凭证） |
| `res_date` | ✓ | `YYYY-MM-DD`，不得早于今天 |
| `slot` | ✓ | 时段 id，0–10 |
| `seat` | ✓ | 座位号，1–17 |
| `agree` | ✓ | 传 `1` 表示已同意须知 |
| `read_seconds` | ✓ | 须知页实际停留秒数，**须 ≥ 5** |
| `sex` / `college` / `grade` |  | 默认 `0` / `10` / `9` |
| `stu_code` / `email` / `note` |  | 选填 |

**成功**
```json
{
  "status": true,
  "data": {
    "uid": 1024, "res_date": "2026-10-19", "slot": 5,
    "slot_label": "14:00-14:40", "seat": 7,
    "meditation_room": "410B", "checkin_room": "412",
    "min_ahead_minutes": 5
  },
  "msg": "预约已提交，请牢记单号 1024"
}
```

**典型失败**
```json
{"status": false, "error": {"seat": "该座位已被预约"}, "msg": "该座位刚被预约，请重新选择"}
{"status": false, "error": {"agree": "阅读《须知与承诺》时长不足，请仔细阅读后再提交"}, "msg": "提交内容有误"}
{"status": false, "error": {}, "msg": "你已有正在处理中的预约，请先完成或取消后再提交"}
```

> 提交后订单状态是「未验证预约」，需值班员在平台上验证后才正式生效，
> 但**座位即刻被占用**，别人无法再选同一时段同一座位。

---

## 5. `POST mpl/list/` — 我的预约

**请求** `{"mobile_phone": "13911112222"}`

**响应**
```json
{
  "status": true,
  "data": {
    "list": [{
      "uid": 1024, "name": "张三", "mobile_phone": "13911112222",
      "res_date": "2026-10-19", "slot": 5, "slot_label": "14:00-14:40", "seat": 7,
      "status": 5, "status_display": "未验证预约",
      "checkin_datetime": null, "checkout_datetime": null,
      "can_cancel": true, "cancel_reason": ""
    }]
  }
}
```

`can_cancel=false` 时 `cancel_reason` 说明原因（如「距开始不足 60 分钟」），可直接提示。

**状态码** `status` 字段的取值：

| 值 | 含义 |
| --- | --- |
| 0 | 预约未完成（等待受理） |
| 1 | 接待未完成（已受理，待到访） |
| 2 | 已完成（已签退） |
| 3 | 作废（已取消/被废弃） |
| 4 | 改约 |
| 5 | 未验证预约（刚提交） |

> 建议**只展示 `status_display` 文案**，别自己映射状态码 —— 避免口径分叉。

---

## 6. `POST cancel/` — 取消

**请求** `{"uid": 1024, "mobile_phone": "13911112222"}`

**成功** `{"status": true, "data": {"uid": 1024}, "msg": "已取消"}`

**失败**
```
{"status": false, "msg": "只能操作本人的预约（请填写预约时使用的手机号）"}
{"status": false, "msg": "距开始不足 60 分钟，请直接联系值班员"}
{"status": false, "msg": "该预约已结束或已取消"}
```

---

## 7. `POST reschedule/` — 改约

**请求**
```json
{"uid": 1024, "mobile_phone": "13911112222",
 "res_date": "2026-10-21", "slot": 2, "seat": 11}
```

**成功**
```json
{"status": true,
 "data": {"uid": 1024, "res_date": "2026-10-21", "slot": 2,
          "slot_label": "10:15-10:55", "seat": 11},
 "msg": "改约成功"}
```

失败情况同 `cancel` / `submit`（占用冲突、时间门槛、手机号不符）。

---

## 身份与权限（需知悉）

网页端**没有登录态**，采用**手机号认领**：

- 查询：输入手机号即返回该号下的预约
- 改约 / 取消：手机号必须与该单登记的一致

**这是弱校验** —— 知道别人手机号的人可以查到并取消其预约。
校园场景下比强制登录现实得多，是经确认的取舍。
要收紧只需在服务端加一道短信验证码。

其他防护：同一手机号只能有 1 个进行中的预约、每时段座位上限 17、按 IP 限流。

---

## 调试建议

- `layout` / `notice` / `slots` **免鉴权且支持 GET**，可直接用浏览器打开验证连通性：
  `https://<平台域名>/meditation/api/layout/`
- 若浏览器控制台报跨域错误 → 找管理员配 `MEDITATION_CORS_ORIGINS`
- ⚠️ **不要在 Windows 命令行里用 curl 传中文 JSON**：终端会把参数转成 GBK，
  导致服务端解析失败而误报「字段必填」。请把请求体写成 UTF-8 文件后用
  `curl --data-binary @file.json`
