# SMUPA 冥想室预约 —— 附加模块

给 SMUPA 工作平台新增的**冥想室预约**功能。
本仓库只包含这一个模块，不含平台其它部分。

---

## ⚠️ 先看这里：这个仓库分两块，给两个人

因为**同学预约页面不在 SMUPA 平台上** —— 它托管在另一个域名上，
通过接口把数据发到 SMUPA 平台。所以是**前后端分离**的两份东西：

```
同学浏览器
   │ 打开 https://kmv-learning-assistant.xyz/meditation/     ← frontend/ 部署在这（开发方托管）
   │ 页面内发请求，跨域
   ▼
SMUPA 平台 https://gzpt.smupa.top/meditation/api/*   ← platform/ 部署在这（管理员部署）
                 ▲
        需要在响应里声明「允许 https://kmv-learning-assistant.xyz 调我」
```

| 目录 | 给谁 | 是什么 | 怎么用 |
| --- | --- | --- | --- |
| **`frontend/`** | **开发方（你自己）** | 纯静态页面（HTML/CSS/JS） | 传到已上线的 `/meditation/` 站点 |
| **`platform/`** | **服务器管理员** | SMUPA 平台侧的代码改动 | 按 `CHANGES.md` 部署 |

**两边都做完，业务才跑通。** 缺任一边：

- 只部署 `platform/` → 平台上什么都没有，同学没地方预约
- 只部署 `frontend/` → 页面能打开，但一提交就报跨域错误

### 文档索引

| 文档 | 给谁 | 内容 |
| --- | --- | --- |
| **`API.md`** | **开发方** | **8 个接口的完整规格**（请求/响应/错误码/鉴权/curl 示例） |
| `CHANGES.md` | 管理员 | 既有文件的逐项改动（含本次新增的咨询预约周历，见第 10 节） |
| **`更新说明.md`** | **管理员** | **已拿过早期版本的话先看这份** —— 只讲增量，含一处**必须重做**的文件 |
| `服务器部署隐患报告.md` | 管理员 | **部署前务必先看** —— 平台自身 5 处既有隐患，本次交付未修改，只报告 |
| `frontend/README.md` | 开发方 | 用现成静态包的话，怎么部署 |
| `tests/` | 管理员 | 端到端集成测试（16 组 / 176 条断言），见 `tests/README.md` |

> **准备上线？直接跳到文末的[《上线前置检查单》](#七上线前置检查单)** ——
> 12 项，两边各自要做的事都列全了，勾完才算真的能跑。

---

## 一、`frontend/` —— 给开发方

**这是本包里的纯静态版**（`Web_4.7.1`），`config.js` 的 `API_BASE` 已指向
`https://gzpt.smupa.top/meditation/api`，**直接传上去即可**。

> ⚠️ **注意线上现在跑的不是这一版。**
> <https://kmv-learning-assistant.xyz/meditation/> 目前还是**早前的过渡版
> `Web_4.7.0`** —— 那一版自带 7 个接口、把预约存在浏览器本地，
> **已作废**（代码留在 `18fb100` 提交里）。
> 纯静态版已经写好并验证，但因**平台侧尚未部署**而压着没切。
> 切换前请先确认管理员侧已完成文末检查单的 1–6 项。

部署（切版）三步，详见 [`frontend/README.md`](frontend/README.md)：

1. `config.js` 的 `API_BASE` **已填好**，通常不用动
2. 确认管理员已把 `https://kmv-learning-assistant.xyz`
   加进平台的 `MEDITATION_CORS_ORIGINS`（见下节 ⚠️ 第 2 条）
3. 把 6 个文件传到 `kmv-learning-assistant.xyz/meditation/`

### ⚠️ 有一条**已废弃的旧方案**，别照做

早期曾规划过「把预约页直接挂在 SMUPA 平台上、入口是
`https://gzpt.smupa.top/meditation/booking/`」。
**这个方案后来废弃了** —— 现在的形态是**页面托管在你们自己的域名上**（上面的地址），
平台侧**没有**任何对外预约页面，`/meditation/booking/` 这个 URL **不存在**。

如果你手上还有那份写着 `/meditation/booking/` 的旧清单（初版《对外预约网页实装清单》），
**请以本仓库的 `API.md` + `README.md` 为准**，不要照那个地址去对接。

---

## 二、`platform/` —— 给服务器管理员

**部署步骤、逐文件改动说明，全在 [`CHANGES.md`](CHANGES.md)。**
这里只给要点。

### 目录

```
platform/
├── new-files/        新增文件，路径已镜像平台结构，可直接覆盖
└── modified-files/   改动过的既有文件（整份，供对照合并）
```

### ⚠️ 三条必须注意的

1. **`modified-files/` 不要整份覆盖**
   里面是改完之后的完整文件。但 `gzpt/settings.py` 很可能含你们自己的真实配置，
   **必须按 `CHANGES.md` 逐项手动合并**。那个目录只是给你对照用的。

2. **一定要配 `MEDITATION_CORS_ORIGINS`，否则同学提交不了**
   ```ini
   MEDITATION_CORS_ORIGINS=https://kmv-learning-assistant.xyz
   ```
   不配的后果：页面能打开，但一点提交就跨域失败。
   **这是本次交付里唯一一个"忘了配就整个功能不可用"的配置项。**

   > ⚠️ **必须一字不差**：中间件是 `origin in allowed` 的**精确字符串匹配**，
   > 而配置解析只做 `strip()`（去空白，**不去尾斜杠**）。
   > 写成 `https://kmv-learning-assistant.xyz/`（多一个尾斜杠）
   > 或带上路径 `/meditation/` **都会静默不匹配** —— 页面照开，提交照样跨域失败，
   > **且不报任何配置错**，极难排查。
   >
   > 浏览器发的 `Origin` 头是 `scheme://host`，**不含路径**，
   > 所以这里填域名根即可，不要带 `/meditation/`。

3. **迁移文件不随包提供，请在服务器自行生成**
   ```bash
   python manage.py makemigrations web
   python manage.py migrate
   ```
   原因见 `CHANGES.md` 末尾。

### 部署后验收

1. 主页出现「**冥想室预约处理**」区块，与上方「**咨询预约处理**」样式一致
   （注意上方原来叫「预约处理」，本次已改名，见 `CHANGES.md` 第 6 节 ①）
2. 咨询预约区块底部多出一排按钮：预约周历 / 预约填写 / 操作历史，
   与冥想室区块那排对称；点「预约周历」应打开 `/consultation/calendar/`
3. 顶部导航出现「冥想室」下拉
4. `/admin/` 里能看到 5 张冥想室表
5. 跨域自检（平台域名已按实际值填好，直接复制即可）：
   ```bash
   # 预检应返回 204 并带 Access-Control-Allow-Origin
   curl -s -D - -o /dev/null -X OPTIONS \
     "https://gzpt.smupa.top/meditation/api/submit/" \
     -H "Origin: https://kmv-learning-assistant.xyz" \
     -H "Access-Control-Request-Method: POST" | grep -i access-control
   ```
6. 打开 <https://kmv-learning-assistant.xyz/meditation/> 走完一遍预约，
   平台上应出现一条「未验证预约」

---

## 三、这个模块做了什么

**对同学**（开发方页面）
按《须知与承诺》（满 5 秒）→ 选日期 → 选时段 → **17 座可视化选座** → 填资料 →
拿到唯一单号；凭手机号可查 / 改约 / 取消。

**对值班员**（SMUPA 平台内，需登录）
主页新增「冥想室预约处理」并列区块；完整处理流：
验证 → 受理 → 签到 → 签退，以及改约 / 废弃 / 清空 / 续约 / 备注。
另有预约列表、待受理、待到访、选座总览、周历、操作历史、打印、满意度调查、分享码。

---

## 四、几个设计决定（接手者可能关心）

### 为什么冥想室**不接** `Res_Room` 房间审批

`Res_Room` 的语义是「**整间房按时间区间排他借用**」，
而冥想室是「**单房间内 17 个座位并行使用**」—— 粒度完全不同。
复用会产生「一人预约即整室被占」的错误语义。

资源冲突由 `(使用日期, 时段档, 座位号)` 三元组表达，并建了复合索引。

### 为什么没有「金山文档（WPS）表单接单」

咨询预约有 3 条**填写入口**：平台内公开页 `/consultation/appointment/`、
值班员代录、以及 `reservation_wps`（金山文档表单推送）。

冥想室只有 **2 条**：

| 咨询预约 | 冥想室对应物 |
| --- | --- |
| `reservation_wps`（外部表单推送） | **`/meditation/api/submit/`** —— 外部页面直接调接口，落库同为「未验证预约」 |
| `new_reservation`（值班员代录） | `new_meditation` |
| `consultation_appointment`（平台内公开页） | **无** —— 有意不提供，页面外置在委托人域名上 |

也就是说 **`submit/` 是 `reservation_wps` 的等价替代**（`meditation_api.py` 的注释里写了
「与 reservation_wps 同构」），不是漏做。外部来源同样**只落库为待验证**，
不直接进入处理流，由值班员验证后才生效 —— 与咨询预约同口径。

### 为什么只提供**一个**问卷数据出口

咨询预约声明了两个：`survey_data` 与 `survey_api_output`。
但 **`survey_data` 是平台里的死代码 + 坏代码**：它没有注册任何路由，
且函数体里 `{{...} for item in survey_set}` 是**对 dict 做集合推导**，
一旦真被执行必抛 `TypeError: unhashable type: 'dict'`（已实测确认）。

所以冥想室**没有照抄它**，只实现了能用的那个
（`/meditation/api/survey/data/<key>/` ↔ `survey_api_output`）。
**这是有意的，不是漏做。**

### 两个房间不是同一个地方

- **冥想室 `410B`** —— 同学实际使用的地方
- **签到值班室 `412`** —— 纸质签到/签退在这里，由值班员引导入室

对应两个独立配置项 `MEDITATION_ROOM` / `MEDITATION_CHECKIN_ROOM`，模板里别混用。

### 时段与座位是固定常量，由接口下发

11 个时段档（每档 40 分钟）与 17 个座位坐标定义在
`platform/new-files/web/meditation_constants.py`，通过 `/layout/` 接口下发给前端。
**前端不硬编码坐标** —— 保证各端座位图不会画得不一样。

### 🚨 按-IP 限流不要用「每人一个 IP」的思路调小

对外接口有按 IP 限流。**校园网 NAT 下同一出口 IP 代表成百上千人**，
阈值是按这个前提取的宽值。调小会**误拦正常同学**。

---

## 五、环境要求

与原平台一致：**Django 1.11.28 / Python 3.8+**。

本模块只用 Django 1.11 支持的 API（如 `django.conf.urls.url`），
未引入任何 2.x 才有的写法。

> 附注：CORS 中间件必须以**字符串路径**注册在 `MIDDLEWARE` 里 ——
> Django 1.11 的 `load_middleware` 会对每一项执行 `import_string()`，
> 直接塞类对象会报 `type object has no attribute 'rsplit'`。

---

## 六、已知的后续项

| 项 | 状态 |
| --- | --- |
| 满意度调查邮件正文 | **机制完整，正文是占位** —— 待业务方提供正式文案后再替换 |
| 黑名单（累计爽约/超时） | `Med_Blacklist` 表已建，**统计逻辑未接线** —— 依赖「值班在岗时段表」，待确定 |
| 身份校验强度 | 手机号弱校验（业务方确认的取舍）；收紧只需改服务端 `_owns()` 一个函数 |
| 小程序入口 | 服务端接口已就绪（`/meditation/api/wxlogin/` 等），小程序工程不包含在本仓库 |

---

## 七、上线前置检查单

**两边都勾完，业务才真的能跑。** 任何一项没做，都会以"页面能开、但某个动作失败"
的形式表现出来，且**多数不报配置错**。

### 管理员侧（SMUPA 平台）

| # | 事项 | 没做的后果 | 详见 |
| --- | --- | --- | --- |
| □ 1 | 按 `CHANGES.md` 逐项合并改动（**`modified-files/` 不要整份覆盖**） | 合并冲突/覆盖掉你们自己的配置 | `CHANGES.md` |
| □ 2 | `.env` 配 `MEDITATION_CORS_ORIGINS=https://kmv-learning-assistant.xyz` | **同学一点提交就跨域失败**（唯一"忘了配就完全不可用"的项） | `CHANGES.md` 第 0 节 |
| □ 3 | 服务器上生成迁移并执行 `makemigrations web` + `migrate` | 冥想室相关表不存在，页面 500 | `CHANGES.md` 迁移节 |
| □ 4 | **把 2 个新增 CSS 手工拷进生产静态目录**（**别用 `collectstatic`**） | 页面样式全乱（裸 HTML） | `CHANGES.md` 静态文件节 |
| □ 5 | 重启服务 | `.env` 与代码改动不生效 | — |
| □ 6 | 先读 `服务器部署隐患报告.md`（平台自身 5 处既有隐患） | 新建环境可能冷启动就炸 | 该报告 |

### 开发方侧（委托人）

| # | 事项 | 没做的后果 | 详见 |
| --- | --- | --- | --- |
| □ 7 | 拿到**管理员给的平台真实域名**，写进页面配置 | 接口打不通 | `API.md` ★ 节 |
| □ 8 | 页面里把 `email` 设为**必填** | 该单的满意度调查**永远发不出去，且无提示** | `API.md` `submit/` 节 |
| □ 9 | 部署后逐条走一遍：取须知 → 选座 → 提交 → 查我的预约 → 改约 → 取消 | — | `API.md` 调试建议 |

### 联调（两边一起）

| # | 事项 | 详见 |
| --- | --- | --- |
| □ 10 | 浏览器打开 `https://gzpt.smupa.top/meditation/api/layout/`，能看到 JSON 即接口通 | `API.md` 调试建议 |
| □ 11 | 真实提交一单，平台上应出现一条「未验证预约」 | README 验收节 |
| □ 12 | 值班员走完 验证 → 受理 → 签到 → 签退，同学侧再查应显示「已完成」 | `tests/` |
