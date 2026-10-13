# 冥想室预约 · 前端静态包

**你的预约页已上线**：<https://kmv-learning-assistant.xyz/meditation/>
本包是同一份页面，可作对接参照；需要重新部署时按下面的步骤走。
不依赖任何后端、不需要 Node、不需要构建。

---

## 一、怎么用（3 步）

### 1. 改 `config.js`

整个包里**只有这一个文件需要改**：

```js
window.MED_CONFIG = {
  API_BASE: 'https://<SMUPA平台域名>/meditation/api',
  ...
};
```

- 必须是 **https**
- 结尾**不要**带斜杠
- 结尾必须是 `/meditation/api`

> 没改的话页面会直接提示「尚未配置接口地址」，不会让同学白填半天。

### 2. 让管理员放行你的域名

把这个地址发给管理员，让他加进 SMUPA 平台的 `.env`：

```ini
MEDITATION_CORS_ORIGINS=https://kmv-learning-assistant.xyz
```

> ⚠️ **不配这步，页面能打开，但一点提交就报错。**
> 原因：浏览器的同源策略会拦住跨域请求 —— 你的页面在一个域名，
> 接口在另一个域名，平台必须明确声明「允许你这个域名调我」。
>
> 填的是**你这个页面所在的域名**，不是平台域名。
> 有多个域名（比如正式 + 测试）用英文逗号分隔。

### 3. 上传这 6 个文件到你站点的根目录

```
index.html
my.html
config.js
assets/style.css
assets/app.js
assets/my.js
```

保持这个目录结构（`assets/` 是子目录）。上传完直接访问 `https://你的域名/` 即可。

---

## 二、目录说明

| 文件 | 作用 |
| --- | --- |
| `index.html` | 预约页：须知 → 选日期 → 选时段 → 选座 → 填资料 → 拿单号 |
| `my.html` | 我的预约：凭手机号查询 / 改约 / 取消 |
| `config.js` | ★ 唯一要改的配置 |
| `assets/style.css` | 样式（移动端优先，最大宽度 480px 居中） |
| `assets/app.js` | 预约页逻辑 |
| `assets/my.js` | 我的预约页逻辑 |

**两侧标签栏可互相跳转**（`index.html` ↔ `my.html`），不需要额外配置。

---

## 三、常见问题

**Q：打开页面提示「尚未配置接口地址」**
`config.js` 的 `API_BASE` 还是占位值，改成平台地址即可。

**Q：页面能打开，但一点提交就报错**
九成是**跨域没放行**。错误提示里会写明。把这一步交给管理员：

```
MEDITATION_CORS_ORIGINS=https://kmv-learning-assistant.xyz
```

注意要带 `https://`、不带结尾斜杠、且是**页面所在域名**而非接口域名。
改完要**重启平台服务**才生效。

**Q：为什么同学侧只有手机号能查预约？不怕别人乱取消吗**
这是与业务方确认过的取舍：校园场景下要人人登录成本太高。
现有防护：同一手机号只能有一个进行中的预约、每时段座位上限 17、
按 IP 限流。要收紧验证只需在服务端加一道短信验证码。

**Q：能不能放多个子域名（比如一个测试环境）**
可以，`MEDITATION_CORS_ORIGINS` 用英文逗号分隔，例如：
```
MEDITATION_CORS_ORIGINS=https://med.your-domain.com,https://med-test.your-domain.com
```

**Q：接口地址能写成域名根路径吗（不带 /meditation/api）**
不能，接口就挂在 `/meditation/api/` 下。

**Q：Cloudflare 上要注意什么**
- 走 Cloudflare 代理没问题，但要确保**最终是 HTTPS**
- 如果开了「Always Use HTTPS」更稳妥
- 不要给这个站点套需要登录的 Cloudflare Access，否则同学进不来

---

## 四、本地先自测（可选）

不必等管理员配好就能自测：

```bash
# 在这个目录下起一个静态服务
python -m http.server 8080
# 然后浏览器打开 http://127.0.0.1:8080/
```

再把 `config.js` 的 `API_BASE` 临时指向平台的测试地址。
若页面报跨域错误，说明管理员那边还没放行你本地这个地址 —— 属于预期。
