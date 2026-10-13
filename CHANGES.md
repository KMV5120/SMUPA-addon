# 既有文件的改动清单（给服务器管理员）

本模块除了新增文件，还需要对平台**既有的 9 个文件**做改动。
**全部是追加，既有代码逻辑一行未改。**

> ⚠️ `platform/modified-files/` 里是**改完之后的完整文件**。
> 但 `gzpt/settings.py` 很可能含你们自己的真实配置（邮箱密码、密钥等），
> **请按下面的说明手动合并，不要整份覆盖**。那个目录只是给你对照用的。

---

## 0. ★ 最重要的一件事：跨域配置

**同学预约页面不在本平台上** —— 它托管在另一个域名上，通过接口把数据发过来。
浏览器会拦住跨域请求，必须在平台上放行那个域名，否则**同学一点提交就失败**。

```ini
# .env
MEDITATION_CORS_ORIGINS=https://kmv-learning-assistant.xyz
```

- 填**页面所在的域名**（不是本平台域名），带协议、不带结尾斜杠
- 多个用英文逗号分隔
- **留空 = 不开放**（默认安全）
- 改完要**重启服务**

> ⚠️ **必须一字不差**：中间件是 `origin in allowed` 的**精确字符串匹配**，
> 配置解析只做 `strip()`（去空白，**不去尾斜杠**）。
> 写成 `https://kmv-learning-assistant.xyz/`（多尾斜杠）或带路径 `/meditation/`
> 都会**静默不匹配** —— 页面照开、提交照样跨域失败，且不报任何配置错。
> 浏览器发的 `Origin` 头是 `scheme://host`，不含路径，填域名根即可。

> 这是本次交付里唯一一个「忘了配就整个功能不可用」的配置项。

---

## 1. `gzpt/settings.py`

### ① `MIDDLEWARE` 首位插入跨域中间件（第 57 行）

```python
MIDDLEWARE = [
    # 冥想室对外接口的跨域放行。放在最外层：响应阶段它最后执行，
    # 保证 CORS 头不会被其它中间件覆盖。只作用于 /meditation/api/。
    'web.middleware.meditation_cors.MeditationCorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    ...（其余保持不变）
]
```

**必须放在第一位**（响应阶段最后执行，CORS 头才不会被覆盖）。
**必须写字符串路径** —— Django 1.11 的 `load_middleware` 会对每一项执行
`import_string()`，直接塞类对象会报 `type object has no attribute 'rsplit'`。

### ② `WHITE_REGEX_URL_LIST` 追加 3 条（第 228 行附近）

```python
    # 冥想室：对外接口（同学预约页面跨域调用，自行用手机号或签名 token 鉴权）
    '^/meditation/api/',
    '^/meditation/share/visit/',
    '^/meditation/survey/',
```

**不加这几条，同学页面调接口会被中间件重定向到登录页。**
注意：平台端页面（列表/详情/周历等）**不在白名单里，仍需登录** —— 这是刻意的。

### ③ 新增冥想室配置项（第 189-208 行，建议放在 `MASSAGE_DEVICE_MAP` 之后）

```python
# 冥想室（平台端 + 微信小程序）
MEDITATION_MINIPROGRAM_APPID = os.environ.get('MEDITATION_MP_APPID', '')
MEDITATION_MINIPROGRAM_SECRET = os.environ.get('MEDITATION_MP_SECRET', '')
MEDITATION_API_KEY = os.environ.get('MEDITATION_API_KEY', '')
# 冥想室与签到值班室是两个不同的地方，分开配置
MEDITATION_ROOM = os.environ.get('MEDITATION_ROOM', '410B')
MEDITATION_CHECKIN_ROOM = os.environ.get('MEDITATION_CHECKIN_ROOM', '412')
# 对外接口按-IP 限流（校园网 NAT 下同 IP 代表很多人，阈值要取宽；0=关闭）
MEDITATION_SUBMIT_LIMIT_PER_IP = int(os.environ.get('MEDITATION_SUBMIT_LIMIT_PER_IP', '60') or 0)
MEDITATION_LIST_LIMIT_PER_IP = int(os.environ.get('MEDITATION_LIST_LIMIT_PER_IP', '300') or 0)
# ★ 允许跨域调用 /meditation/api/ 的来源（逗号分隔）。留空 = 不开放。
MEDITATION_CORS_ORIGINS = [o.strip() for o in
                           os.environ.get('MEDITATION_CORS_ORIGINS', '').split(',')
                           if o.strip()]
```

> 小程序相关的 3 项（`MEDITATION_MP_APPID` / `_SECRET` / `MEDITATION_API_KEY`）
> **现在不配也行** —— 它们只在将来启用小程序时才用。

---

## 2. `web/models.py`

### ① 顶部 import（第 10 行附近，`from multiselectfield import ...` 之后）

```python
from web.meditation_constants import (
    MEDITATION_SLOTS,
    MEDITATION_SEAT_CHOICES,
)
```

### ② 文件末尾追加整个冥想室模型段（第 641 行起，约 260 行）

包含 4 个常量 + 5 个模型：

| 模型 | 对应心理预约的 |
| --- | --- |
| `Med_Reservation` | `Reservation` |
| `Med_Form_Data` | `Res_Form_Data` |
| `Med_Operation` | `Operation` |
| `Med_Share` | `ResShare` |
| `Med_Blacklist` | （新增，本期只建表不接线） |

**整段追加即可，不需改动上面任何既有代码。**

---

## 3. `web/urls.py`

### ① 顶部 import（第 17 行）追加两个模块

```python
from web.views import account, reservation, notification, room, datashow, beta, pusher, meditation, meditation_api
```

### ② `urlpatterns` 末尾追加（第 116 行起，约 42 行）

平台端 17 条 + 对外接口 8 条，全部以 `meditation/` 开头，与既有路由无冲突。

> 注意：**平台端没有对外预约页面** —— 同学页面由开发方托管在另一个域名上。
> 本平台只提供接口。

### ③ 另在既有路由区追加 1 条咨询预约周历路由（第 61 行附近）

这次的改动**不在文件末尾**，而是在既有的咨询预约路由旁边（`/calendar/` 之后）：

```python
# 咨询预约周历（栅格版，与上面 /calendar/ 并存，互不影响）
url(r'^consultation/calendar/$', reservation.consultation_calendar, name='consultation_calendar'),
```

> **既有的 `/calendar/` 一行未动**，两条路由并存：
> `/calendar/` 是平台原有的「小时时间轴」版，`/consultation/calendar/` 是本次新增的栅格版。
> 见第 10 节。

---

## 4. `web/admin.py`

### ① 追加 5 个 ModelAdmin 类（第 106-144 行附近）
### ② 注册（第 161 行附近）

```python
# 冥想室预约
admin.site.register(Med_Reservation, admin_Med_Reservation)
admin.site.register(Med_Form_Data, admin_Med_Form_Data)
admin.site.register(Med_Operation, admin_Med_Operation)
admin.site.register(Med_Share, admin_Med_Share)
admin.site.register(Med_Blacklist, admin_Med_Blacklist)
```

> 文件顶部已有 `from web.models import *`，无需再加 import。

---

## 5. `web/views/account.py`

`dashboard()` 视图内追加冥想室统计（第 153 行附近，
放在 `notify_list = models.Notification.objects.all()[:6]` **之前**），约 19 行。

`render` 用的是 `locals()`，**无需改 `return render(...)`**。

---

## 6. `web/templates/dashboard.html`

这个文件有**三处**改动。

### ① 把一个标题改名（**唯一一处改到既有文字的地方**）

第 27 行，既有的咨询预约区块标题：

```diff
-            <h3 class="mb-5">预约处理</h3>
+            <h3 class="mb-5">咨询预约处理</h3>
```

原因：下方新增的冥想室区块叫「冥想室预约处理」，两个都叫「预约处理」会分不清。

> 只改了这一处**显示文字**，没有改它的 `id="number"`、类名或任何逻辑。

### ② 给咨询预约区块补一排按钮（第 80 行附近，约 18 行）

在该区块 `</div>`（数字卡片行结束）与 `</div></div></section>` 之间插入：

```html
<div class="mt-4">
    <a role="button" class="btn btn-sm btn-outline-secondary"
       href="{% url 'consultation_calendar' %}">… 预约周历</a>
    <a role="button" class="btn btn-sm btn-outline-secondary"
       href="{% url 'new_reservation' %}">… 预约填写</a>
    <a role="button" class="btn btn-sm btn-outline-secondary"
       href="{% url 'operate_history' %}">… 操作历史</a>
</div>
```

与下方冥想室区块那排按钮**同三样、同顺序、同类名**，两区块视觉对称。

### ③ 插入冥想室区块（第 84-152 行附近，约 69 行）

在既有 `<section id="number">…</section>` 与 `<section id="info">`
**之间**插入新块。

> ⚠️ **必须用 `{% comment %}` 而不是多行 `{# #}`** ——
> Django 1.11 的模板正则没有 `re.DOTALL`，多行 `{# #}` **不是注释**，
> 文字会原样泄漏到页面上。

---

## 7. `web/templates/layout/basic.html`

在「预约菜单」下拉的 `</li>` 之后、「房间管理」下拉之前插入
（第 172 行附近，约 22 行）：新增一个 `id="med-menu"` 的下拉。

---

## 8. `utils/validate_tools.py`

文件末尾追加两个函数（第 19、34 行起，约 25 行）：

```python
def validate_date_format(text):   # 校验 'YYYY-MM-DD'
def parse_date(text):             # 解析成 date，非法返回 None
```

> 既有的 `validate_datetime_format` 只认 `'%Y-%m-%d %H:%M'`，
> 冥想室用「日期 + 时段档」，不能复用它。

---

## 9. `.env.example`

末尾追加冥想室相关变量（约 30 行），其中 **`MEDITATION_CORS_ORIGINS` 见第 0 节**。
`.env.example` 只是示例文件，不含真实值，直接追加即可。

---

## 10. `web/views/reservation.py` ＋ 新增 1 页 1 样式（咨询预约周历）

这一节与前 9 节**不是同一个功能** —— 前 9 节是冥想室模块，
这一节是给**平台原有的咨询预约**加一个栅格式周历，与冥想室无关。

### ① `web/views/reservation.py`：追加 1 个视图函数

在既有 `def calendar(request):` **之后**、`def consultation_appointment(request):`
**之前**插入（约 71 行）：

```python
def consultation_calendar(request):
    """本周咨询预约周历（栅格式）。"""
```

> **既有的 `calendar()` 一行未改**，两条路由并存。

### ② 新增文件 `web/templates/reservation/consultation_calendar.html`（约 76 行）

### ③ 新增文件 `static/css/reservation_calendar.css`（约 106 行）

> 样式**刻意不共用**冥想室的 `meditation.css`，而是独立一份：
> 咨询预约是平台原有模块，不该依赖附加的冥想室模块 ——
> 哪天拿掉冥想室，这个页面也必须照常好看。

### 为什么不直接改造原有的 `/calendar/`

原有的 `/calendar/` 是「**小时时间轴**」版（左侧 7:00–20:00 刻度、右侧七天列），
样式与冥想室周历完全不同。**为避免动到平台既有页面**，本次新增一页而不是替换，
两个版本并存，按导航入口各取所需。

### 与原有版本的一处行为差异（有意为之）

咨询时间存在 `Res_Form_Data.res_datetime` 这个**字符串**字段里，
没法在 DB 层按日期区间过滤，只能在 Python 侧解析归周。
原有那版遇到一条（status=1 的）格式坏的单，会**整页替换成错误页**
（HTTP 仍是 200，但周历完全看不到了 —— 已实测确认）；
新版改为**跳过坏数据继续渲染**，并在页面顶部提示有几条被跳过。

---

## ⚠️ 关于数据库迁移

**本包不含迁移文件**，部署时在服务器上自行生成：

```bash
python manage.py makemigrations web
python manage.py migrate
```

原因：本仓库的 `.gitignore` 按设计忽略 `*/migrations/*.py`；
且平台首次 `makemigrations` 生成的 `0001_initial` 会包含**全部既有模型**，
若你的服务器已有自己的迁移记录，直接套用会发生依赖冲突。
由服务器自己生成是唯一稳妥的做法。

---

## 改动量汇总

| 文件 | 改动量 |
| --- | --- |
| `gzpt/settings.py` | +1 中间件、+3 白名单、+16 配置 |
| `web/models.py` | +1 import、+260 行模型 |
| `web/urls.py` | +1 模块、+42 行冥想室路由、+1 行咨询周历路由 |
| `web/admin.py` | +39 行 |
| `web/views/account.py` | +19 行 |
| `web/templates/dashboard.html` | +1 处标题改名、+18 行按钮、+69 行冥想室区块 |
| `web/templates/layout/basic.html` | +22 行 |
| `utils/validate_tools.py` | +25 行 |
| `.env.example` | +30 行 |
| `web/views/reservation.py` | +71 行（咨询预约周历视图） |
| `web/templates/reservation/consultation_calendar.html` | 新增，约 76 行 |
| `static/css/reservation_calendar.css` | 新增，约 106 行 |

### 对既有代码的改动

**只有一处**：`dashboard.html` 里咨询预约区块的标题
`预约处理` → `咨询预约处理`（纯显示文字，第 6 节 ①）。
其余全部是**追加**，没有改动任何既有函数、模型字段或页面逻辑。

> 另核对过：本次新增的 `consultation_calendar` 视图与原有的 `calendar()` 视图
> 并存于 `reservation.py`，后者**一行未动**。
