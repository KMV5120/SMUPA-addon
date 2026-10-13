/**
 * ★★★ 这个文件是整个前端包里【唯一需要你改】的地方 ★★★
 *
 * API_BASE **已经按管理员提供的平台地址填好了**，通常不用再动。
 * 只有在平台换域名时才需要改这里。
 *
 * 要求：
 *   1. 必须是 https（http 的页面调 https 接口会被浏览器拦）
 *   2. 域名要写全，带协议，**结尾不要带斜杠**
 *   3. 结尾必须是 /meditation/api
 *
 * 例：
 *   API_BASE: 'https://gzpt.smupa.top/meditation/api'
 *
 * ⚠️ 改完之后，必须让**管理员**在 SMUPA 平台的 .env 里把你的域名加进
 *    MEDITATION_CORS_ORIGINS，否则浏览器会拦掉请求（页面能开，但一提交就报错）。
 *    要填的是你**这个页面所在的域名**，不是接口域名。例：
 *      MEDITATION_CORS_ORIGINS=https://med.your-domain.com
 */
window.MED_CONFIG = {

  // ★ 已填好：SMUPA 平台接口地址
  API_BASE: 'https://gzpt.smupa.top/meditation/api',

  // 页面标题（显示在浏览器标签页）
  SITE_NAME: '冥想室预约',

  // 超时（毫秒）。网络慢可调大
  TIMEOUT: 15000,
};
