/* ==========================================================================
   「我的预约」页逻辑

   与 index.html 的 assets/app.js 共用 config.js 与 style.css。
   身份是**手机号弱校验**：查出该手机号下的预约，改约/取消时把手机号一并送出，
   由服务端比对。知道别人手机号的人可以操作他人预约 —— 这是与业务方
   确认过的取舍（校园场景下比强制登录现实得多）。
   ========================================================================== */
(function () {
    'use strict';

    var CFG = window.MED_CONFIG || {};
    var API = (CFG.API_BASE || '').replace(/\/+$/, '');
    var TIMEOUT = CFG.TIMEOUT || 15000;
    var phone = '';

    function $(id) { return document.getElementById(id); }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function toast(msg) {
        var d = document.createElement('div');
        d.textContent = msg;
        d.style.cssText = 'position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);' +
            'background:rgba(0,0,0,.8);color:#fff;padding:12px 18px;border-radius:8px;' +
            'font-size:14px;z-index:9999;max-width:82%;text-align:center;line-height:1.6';
        document.body.appendChild(d);
        setTimeout(function () { d.remove(); }, 3000);
    }

    function api(path, method, body) {
        var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
        var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, TIMEOUT) : null;

        return fetch(API + path, {
            method: method || 'GET',
            headers: { 'Content-Type': 'application/json' },
            body: method === 'POST' ? JSON.stringify(body || {}) : undefined,
            signal: ctrl ? ctrl.signal : undefined,
        }).then(function (r) {
            if (timer) { clearTimeout(timer); }
            return r.json().catch(function () {
                return { status: false, msg: '服务器返回异常（HTTP ' + r.status + '）' };
            });
        }, function (err) {
            if (timer) { clearTimeout(timer); }
            var msg = (err && err.name === 'AbortError')
                ? '请求超时，请检查网络后重试'
                : '无法连接服务器。可能原因：① 网络不通；' +
                  '② 服务器尚未放行本页面的跨域访问（需管理员把本页面域名加进 MEDITATION_CORS_ORIGINS）';
            throw { status: false, msg: msg, _network: true };
        });
    }

    function render(items) {
        if (!items.length) {
            $('list').innerHTML = '<div class="mb-empty">没有查询到预约记录<br>' +
                '<span style="font-size:12px">请确认手机号与预约时填写的一致</span></div>';
            return;
        }
        $('list').innerHTML = items.map(function (it) {
            var actions = '';
            if (it.can_cancel) {
                actions = '<div class="mb-res-actions">' +
                    '<button class="mb-mini" data-act="reschedule" data-uid="' + it.uid + '">改约</button>' +
                    '<button class="mb-mini danger" data-act="cancel" data-uid="' + it.uid + '">取消预约</button>' +
                    '</div>';
            } else if (it.cancel_reason) {
                actions = '<div class="mb-res-actions"><button class="mb-mini" disabled>' +
                    esc(it.cancel_reason) + '</button></div>';
            }
            return '<div class="mb-res s' + it.status + '">' +
                '<div class="mb-res-head">' +
                '<span class="mb-res-uid">' + it.uid + ' 号单</span>' +
                '<span class="mb-res-status">' + esc(it.status_display) + '</span></div>' +
                '<div class="mb-res-body">' + esc(it.res_date) + ' · ' + esc(it.slot_label) +
                ' · ' + it.seat + ' 号座</div>' +
                (it.checkin_datetime ? '<div class="mb-res-body" style="color:#37b24d">已签到 ' +
                    esc(it.checkin_datetime) + '</div>' : '') +
                actions + '</div>';
        }).join('');
    }

    function search() {
        phone = $('phone').value.trim();
        if (!/^1[3-9]\d{9}$/.test(phone)) { toast('请输入正确的手机号'); return; }
        try { localStorage.setItem('med_phone', phone); } catch (e) {}
        $('tip').textContent = '查询中…';
        api('/mpl/list/', 'POST', { mobile_phone: phone }).then(function (res) {
            if (!res.status) {
                $('tip').textContent = '';
                toast(res.msg || '查询失败');
                $('list').innerHTML = '';
                return;
            }
            $('tip').textContent = '';
            render((res.data && res.data.list) || []);
        }).catch(function (err) {
            $('tip').textContent = '';
            toast((err && err.msg) || '网络异常，请重试');
        });
    }

    function doCancel(uid) {
        if (!confirm('确认取消该预约？取消后座位将释放给其他同学。')) return;
        api('/cancel/', 'POST', { uid: uid, mobile_phone: phone }).then(function (res) {
            toast(res.msg || (res.status ? '已取消' : '取消失败'));
            if (res.status) { search(); }
        }).catch(function (err) {
            toast((err && err.msg) || '网络异常，请重试');
        });
    }

    function doReschedule(uid) {
        // 跳回预约页，带上原单号与手机号，走一遍“重新选日期/时段/座位”的流程
        location.href = 'index.html?mode=reschedule&uid=' + uid +
            '&phone=' + encodeURIComponent(phone);
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!API || API.indexOf('REPLACE-ME') !== -1) {
            document.body.innerHTML =
                '<div style="max-width:480px;margin:80px auto;padding:24px;font-family:sans-serif;' +
                'line-height:1.8;color:#212529">' +
                '<h3 style="color:#e03131">尚未配置接口地址</h3>' +
                '<p>请打开 <code>config.js</code>，把 <code>API_BASE</code> 改成 ' +
                'SMUPA 平台的地址（形如 <code>https://平台域名/meditation/api</code>）。</p>' +
                '</div>';
            return;
        }

        $('btnSearch').addEventListener('click', search);
        $('phone').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { search(); }
        });
        $('list').addEventListener('click', function (e) {
            var t = e.target.closest('button[data-act]');
            if (!t) { return; }
            var uid = Number(t.dataset.uid);
            if (t.dataset.act === 'cancel') { doCancel(uid); }
            if (t.dataset.act === 'reschedule') { doReschedule(uid); }
        });

        // 从结果页或上次访问带过来的手机号，自动查一次
        var q = new URLSearchParams(location.search);
        var pre = q.get('phone');
        if (!pre) { try { pre = localStorage.getItem('med_phone'); } catch (e) {} }
        if (pre) {
            $('phone').value = pre;
            search();
        }
    });
})();
