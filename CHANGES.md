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
MEDITATION_CORS_ORIGINS=https://<开发方的子域名>
```

- 填**页面所在的域名**（不是本平台域名），带协议、不带结尾斜杠
- 多个用英文逗号分隔
- **留空 = 不开放**（默认安全）
- 改完要**重启服务**

> 这是本次交付里唯一一个「忘了配就整个功能不可用」的配置项。

---

## 1. `gzpt/settings.py`

### ① `MIDDLEWARE` 首位插入跨域中间件（第 57 行）

```python
MIDDLEWARE = [
    # 冥想室对外接口的跨域放行。放在**最外层**：响应阶段它最后执行，
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

在既有 `<section id="number">…</section>`（预约处理）与 `<section id="info">`
**之间**插入新块（第 84-152 行附近，约 69 行）。

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
| `web/urls.py` | +1 模块、+42 行路由 |
| `web/admin.py` | +39 行 |
| `web/views/account.py` | +19 行 |
| `web/templates/dashboard.html` | +69 行 |
| `web/templates/layout/basic.html` | +22 行 |
| `utils/validate_tools.py` | +25 行 |
| `.env.example` | +30 行 |

**既有代码逻辑一行未改**，全部是追加。
