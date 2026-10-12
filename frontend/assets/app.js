/* ==========================================================================
   冥想室对外预约页（免登录 H5）

   设计要点
   --------
   1. 复用小程序那套接口（/meditation/api/*），服务端契约完全一样，
      因此两端行为一致、只有 UI 不同。
   2. 接口是 @csrf_exempt 且免登录的，页面用相对路径调用，同源无跨域问题。
   3. 座位坐标、时段表、选项（学院/年级/性别）全部由 /layout/ 下发，
      页面内**不硬编码任何业务数据**。
   ========================================================================== */
(function () {
    'use strict';

    // API 基址来自 config.js（本包唯一需要改的文件）
    var CFG = window.MED_CONFIG || {};
    var API = (CFG.API_BASE || '').replace(/\/+$/, '');
    var TIMEOUT = CFG.TIMEOUT || 15000;

    // 没配好就不让往下走，免得同学填半天才发现提交不了
    if (!API || API.indexOf('REPLACE-ME') !== -1) {
        document.addEventListener('DOMContentLoaded', function () {
            document.body.innerHTML =
                '<div style="max-width:480px;margin:80px auto;padding:24px;font-family:sans-serif;' +
                'line-height:1.8;color:#212529">' +
                '<h3 style="color:#e03131">尚未配置接口地址</h3>' +
                '<p>请打开 <code>config.js</code>，把 <code>API_BASE</code> 改成 ' +
                'SMUPA 平台的地址（形如 <code>https://平台域名/meditation/api</code>）。</p>' +
                '</div>';
        });
        return;
    }

    var S = {
        step: 'loading',
        layout: null,
        noticeReadSeconds: 5,
        readElapsed: 0,
        canAgree: false,
        mode: 'new',        // new | reschedule
        uid: null,
        phone: '',
        date: '',
        slot: null,
        slotLabel: '',
        seat: 0,
        seats: [],
        taken: [],
        _first: true,   // 首次渲染用 replaceState，避免产生多余的历史记录
    };

    /* ---------------- 通用 ---------------- */
    function $(id) { return document.getElementById(id); }

    function pad(n) { return (n < 10 ? '0' : '') + n; }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function toast(msg) {
        var d = document.createElement('div');
        d.textContent = msg;
        d.style.cssText = 'position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);' +
            'background:rgba(0,0,0,.78);color:#fff;padding:10px 18px;border-radius:8px;' +
            'font-size:14px;z-index:9999;max-width:80%;text-align:center;line-height:1.5';
        document.body.appendChild(d);
        setTimeout(function () { d.remove(); }, 2400);
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
            // 跨域被拦住时，浏览器只抛一个信息极少的 TypeError，
            // 这里翻译成同学和值班员都能看懂的说法。
            var msg = (err && err.name === 'AbortError')
                ? '请求超时，请检查网络后重试'
                : '无法连接服务器。可能原因：① 网络不通；' +
                  '② 服务器尚未放行本页面的跨域访问（需管理员把本页面域名加进 MEDITATION_CORS_ORIGINS）';
            throw { status: false, msg: msg, _network: true };
        });
    }

    /* ---------------- 步骤切换 ----------------
       为了让**手机/浏览器的返回键**也能逐步回退（而不是直接退出页面），
       每进入一步都往 history 里压一条记录，并监听 popstate 回到对应步骤。
       结果页用 replaceState：预约已完成，返回键应该离开页面而不是回到表单。 */
    var ORDER = ['notice', 'date', 'slot', 'seat', 'form'];

    function show(step, opts) {
        opts = opts || {};
        S.step = step;

        ['loading', 'notice', 'date', 'slot', 'seat', 'form', 'result'].forEach(function (k) {
            var el = $('panel-' + k);
            if (el) el.hidden = (k !== step);
        });
        $('stepBar').style.display = (step === 'result' || step === 'loading') ? 'none' : 'flex';

        var idx = ORDER.indexOf(step);
        Array.prototype.forEach.call(document.querySelectorAll('.mb-step'), function (el) {
            var i = ORDER.indexOf(el.dataset.step);
            el.classList.toggle('done', i >= 0 && i < idx);
            el.classList.toggle('active', i === idx);
        });

        // 第一步没有"返回上一步"，其余步骤显示
        $('btnBack').hidden = !(idx > 0);

        if (!opts.noHistory) {
            // 首次渲染 & 结果页都用 replace：前者不该产生多余历史，
            // 后者预约已完成，返回键应离开页面而不是回到表单。
            if (opts.replace || S._first) {
                history.replaceState({ step: step }, '');
                S._first = false;
            } else {
                history.pushState({ step: step }, '');
            }
        }
        window.scrollTo(0, 0);
    }

    // 返回键 / 返回按钮统一走这里：交给 history，由 popstate 统一处理
    function goBack() {
        history.back();
    }

    window.addEventListener('popstate', function (e) {
        var st = (e.state && e.state.step) || ORDER[0];
        show(st, { noHistory: true });
    });

    /* ---------------- 初始化 ---------------- */
    function init() {
        // 支持「我的预约」页跳过来改约：?mode=reschedule&uid=N&phone=xxx
        var q = new URLSearchParams(location.search);
        S.mode = q.get('mode') === 'reschedule' ? 'reschedule' : 'new';
        S.uid = q.get('uid') ? Number(q.get('uid')) : null;
        S.phone = q.get('phone') || '';
        if (S.mode === 'reschedule') {
            $('headSub').textContent = '改约 · 请重新选择日期与座位';
        }

        api('/layout/').then(function (res) {
            if (!res.status) { toast(res.msg || '加载失败'); return; }
            S.layout = res.data;
            var L = S.layout;
            document.title = (L.meditation_room || '410B') + ' 冥想室预约';
            $('headSub').textContent = '冥想室 ' + (L.meditation_room || '410B') +
                ' · 签到值班室 ' + (L.checkin_room || '412');
            buildChoices(L.choices);
            $('roomDoor').style.left = (L.door.x) + '%';
            $('roomDoor').style.top = (L.door.y) + '%';
            renderRoom();
            // 改约模式跳过"须知"（用户已经读过、且当时已记录阅读时长）
            if (S.mode === 'reschedule') { goDate(); } else { loadNotice(); }
        }).catch(function (err) {
            // 跨域没配好是最常见的失败原因，直接把可读信息显示出来，
            // 不要只说"加载失败"让人无从下手
            $('panel-loading').innerHTML =
                '<div class="mb-empty" style="padding:40px 24px;line-height:1.9">'
                + esc((err && err.msg) || '加载失败，请检查网络后刷新重试')
                + '</div>';
        });
    }

    function buildChoices(choices) {
        if (!choices) return;
        fill('f_sex', choices.sex);
        fill('f_college', choices.college, 10);
        fill('f_grade', choices.grade, 9);
    }

    function fill(id, pairs, def) {
        var el = $(id);
        if (!el || !pairs) return;
        el.innerHTML = pairs.map(function (p) {
            return '<option value="' + p[0] + '"' +
                (String(p[0]) === String(def) ? ' selected' : '') + '>' + esc(p[1]) + '</option>';
        }).join('');
    }

    /* ---------------- 1. 须知 ---------------- */
    function loadNotice() {
        api('/notice/').then(function (res) {
            if (!res.status) { show('notice'); return; }
            var d = res.data;
            $('noticeTitle').textContent = d.title || '冥想室使用须知与承诺';
            $('noticeBody').innerHTML = d.html || '';
            S.noticeReadSeconds = d.min_read_seconds || 5;
            startCountdown(S.noticeReadSeconds);
            show('notice');
        }).catch(function () { goDate(); });
    }

    function startCountdown(sec) {
        var remain = sec;
        render();
        var t = setInterval(function () {
            remain -= 1;
            S.readElapsed += 1;
            if (remain <= 0) {
                clearInterval(t);
                S.canAgree = true;
                $('btnAgree').disabled = false;
            }
            render();
        }, 1000);

        function render() {
            $('noticeHint').textContent = S.canAgree ? '已阅读完毕'
                : '请仔细阅读，' + Math.max(0, remain) + ' 秒后可继续';
            $('noticeHint').className = 'mb-hint' + (S.canAgree ? ' ok' : '');
        }
    }

    /* ---------------- 2. 选日期 ---------------- */
    function goDate() {
        var days = 14, out = [];
        var wk = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        var now = new Date();
        for (var i = 0; i < days; i++) {
            var d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
            out.push({
                value: d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()),
                label: pad(d.getMonth() + 1) + '-' + pad(d.getDate()),
                week: i === 0 ? '今天' : (i === 1 ? '明天' : wk[d.getDay()]),
            });
        }
        $('dateGrid').innerHTML = out.map(function (d) {
            return '<div class="mb-date' + (d.value === S.date ? ' on' : '') +
                '" data-v="' + d.value + '"><div class="w">' + d.week +
                '</div><div class="d">' + d.label + '</div></div>';
        }).join('');
        show('date');
    }

    function pickDate(v) {
        S.date = v;
        S.slot = null; S.slotLabel = ''; S.seat = 0;
        goSlot();
    }

    /* ---------------- 3. 选时段 ---------------- */
    function goSlot() {
        api('/slots/?date=' + encodeURIComponent(S.date)).then(function (res) {
            if (!res.status) { toast(res.msg || '获取时段失败'); return; }
            var d = res.data;
            S.taken = d.taken || [];
            var total = d.seat_count || 17;
            $('slotList').innerHTML = (d.per_slot || []).map(function (s) {
                var remain = Math.max(0, total - s.taken);
                return '<div class="mb-slot' + (s.full ? ' full' : '') +
                    (s.slot === S.slot ? ' on' : '') + '" data-slot="' + s.slot + '">' +
                    '<div class="mb-slot-label">' + esc(s.label) + '</div>' +
                    (s.full ? '<div class="mb-slot-full">已约满</div>'
                            : '<div class="mb-slot-ok">剩余 ' + remain + ' 位</div>') +
                    '</div>';
            }).join('');
            show('slot');
        });
    }

    function pickSlot(i) {
        var el = document.querySelectorAll('.mb-slot')[i];
        if (!el || el.classList.contains('full')) { toast('该时段已约满'); return; }
        S.slot = Number(el.dataset.slot);
        S.slotLabel = el.querySelector('.mb-slot-label').textContent;
        S.seat = 0;
        goSeat();
    }

    /* ---------------- 4. 选座位 ---------------- */
    function renderRoom() {
        var room = $('room');
        var L = S.layout;
        var takenNow = {};
        S.taken.forEach(function (p) {
            if (p[0] === S.slot) takenNow[p[1]] = 1;
        });
        // 移除旧座位节点（保留门）
        Array.prototype.slice.call(room.querySelectorAll('.mb-seat')).forEach(function (n) { n.remove(); });
        L.seats.forEach(function (s) {
            var el = document.createElement('div');
            el.className = 'mb-seat' + (takenNow[s.no] ? ' taken' : '') + (s.no === S.seat ? ' on' : '');
            el.style.left = s.x + '%';
            el.style.top = s.y + '%';
            el.dataset.no = s.no;
            el.textContent = s.no;
            room.appendChild(el);
        });
    }

    function goSeat() {
        if (!S.taken.length) {
            api('/slots/?date=' + encodeURIComponent(S.date)).then(function (res) {
                if (res.status) { S.taken = res.data.taken || []; }
                afterSeat();
            });
        } else { afterSeat(); }

        function afterSeat() {
            $('seatTip').textContent = S.date + ' · ' + S.slotLabel;
            renderRoom();
            updateSeatHint();
            show('seat');
        }
    }

    function updateSeatHint() {
        $('seatHint').textContent = S.seat ? ('已选 ' + S.seat + ' 号座') : '请点选座位';
        $('seatHint').className = 'mb-hint' + (S.seat ? ' ok' : '');
        $('btnToForm').disabled = !S.seat;
    }

    function pickSeat(no) {
        var el = document.querySelector('.mb-seat[data-no="' + no + '"]');
        if (!el || el.classList.contains('taken')) { toast('该座位已被预约'); return; }
        S.seat = no;
        Array.prototype.forEach.call(document.querySelectorAll('.mb-seat'), function (n) {
            n.classList.toggle('on', Number(n.dataset.no) === no);
        });
        updateSeatHint();
    }

    /* ---------------- 5. 填资料 ---------------- */
    function goForm() {
        $('summary').innerHTML =
            '<div>' + esc(S.date) + '</div><div>' + esc(S.slotLabel) + '</div>' +
            '<div><b>' + S.seat + ' 号座</b></div>';
        if (S.phone && !$('f_mobile_phone').value) {
            $('f_mobile_phone').value = S.phone;   // 改约时带过来
        }
        $('formHint').textContent = S.mode === 'reschedule' ? '确认后提交改约' : '';
        $('btnSubmit').textContent = S.mode === 'reschedule' ? '确认改约' : '提交预约';
        show('form');
    }

    function submit() {
        var errs = {};
        var name = $('f_name').value.trim();
        var phone = $('f_mobile_phone').value.trim();
        if (!name) errs.f_name = '请填写姓名';
        if (!/^1[3-9]\d{9}$/.test(phone)) errs.f_mobile_phone = '请填写正确的手机号';
        $('e_name').textContent = errs.f_name || '';
        $('e_mobile_phone').textContent = errs.f_mobile_phone || '';
        if (Object.keys(errs).length) { toast('请检查填写内容'); return; }

        var payload = {
            name: name,
            sex: Number($('f_sex').value),
            college: Number($('f_college').value),
            grade: Number($('f_grade').value),
            stu_code: $('f_stu_code').value.trim(),
            mobile_phone: phone,
            email: $('f_email').value.trim(),
            note: $('f_note').value.trim(),
            res_date: S.date,
            slot: S.slot,
            seat: S.seat,
            agree: 1,
            read_seconds: Math.max(S.noticeReadSeconds, S.readElapsed),
        };

        var path = '/submit/';
        if (S.mode === 'reschedule') {
            path = '/reschedule/';
            payload.uid = S.uid;
        } else {
            payload.read_seconds = Math.max(payload.read_seconds, 5);
        }

        $('btnSubmit').disabled = true;
        $('btnSubmit').textContent = '提交中…';

        api(path, 'POST', payload).then(function (res) {
            $('btnSubmit').disabled = false;
            $('btnSubmit').textContent = S.mode === 'reschedule' ? '确认改约' : '提交预约';
            if (!res.status) {
                // 字段级错误就标在字段上，其余用 toast
                var e = res.error || {};
                if (e.name || e.mobile_phone) {
                    $('e_name').textContent = e.name ? (e.name[0] || e.name) : '';
                    $('e_mobile_phone').textContent = e.mobile_phone ? (e.mobile_phone[0] || e.mobile_phone) : '';
                }
                toast(res.msg || '提交失败');
                return;
            }
            showResult(res.data);
        }).catch(function (err) {
            $('btnSubmit').disabled = false;
            $('btnSubmit').textContent = '提交预约';
            toast((err && err.msg) || '网络异常，请重试');
        });
    }

    /* ---------------- 6. 结果 ---------------- */
    function showResult(d) {
        var L = S.layout;
        $('resultTitle').textContent = S.mode === 'reschedule' ? '改约成功' : '预约成功';
        $('resultUid').textContent = d.uid;
        $('resultInfo').innerHTML =
            row('使用日期', d.res_date) +
            row('时段', d.slot_label) +
            row('座位', d.seat + ' 号座') +
            row('冥想室', d.meditation_room) +
            row('签到值班室', d.checkin_room);
        $('resultWarn').innerHTML =
            '<h3>请务必注意</h3>' +
            '<p>· 请至少提前 ' + (d.min_ahead_minutes || 5) + ' 分钟到 ' +
            esc(d.checkin_room) + ' 值班室现场纸质签到</p>' +
            '<p>· 由值班员引导进入 ' + esc(d.meditation_room) +
            ' 冥想室，请配合阅读《入门须知》并穿戴鞋套</p>' +
            '<p>· 使用结束后请至 ' + esc(d.checkin_room) + ' 值班室签退，配合清场检查</p>' +
            '<p>· 需改约或取消请至少提前 60 分钟在「我的预约」里操作</p>';
        $('btnGoMy').onclick = function () {
            location.href = 'my.html?phone=' + encodeURIComponent($('f_mobile_phone').value.trim());
        };
        // replace：预约已完成，返回键应离开页面而不是回到表单
        show('result', { replace: true });

        function row(k, v) {
            return '<div class="mb-info-row"><span class="k">' + esc(k) +
                '</span><span>' + esc(v == null ? '—' : v) + '</span></div>';
        }
    }

    /* ---------------- 事件绑定 ---------------- */
    function bind() {
        $('btnAgree').addEventListener('click', goDate);
        $('dateGrid').addEventListener('click', function (e) {
            var t = e.target.closest('.mb-date');
            if (t) pickDate(t.dataset.v);
        });
        $('slotList').addEventListener('click', function (e) {
            var t = e.target.closest('.mb-slot');
            if (!t) return;
            var i = Array.prototype.indexOf.call(document.querySelectorAll('.mb-slot'), t);
            pickSlot(i);
        });
        $('room').addEventListener('click', function (e) {
            var t = e.target.closest('.mb-seat');
            if (t) pickSeat(Number(t.dataset.no));
        });
        $('btnToForm').addEventListener('click', goForm);
        $('btnSubmit').addEventListener('click', submit);
        // 返回：三处入口统一走 goBack()，交给 history 处理，
        // 这样"点按钮返回"与"按手机返回键"行为完全一致
        $('btnBack').addEventListener('click', goBack);
        $('btnBackSeat').addEventListener('click', goBack);
        $('btnBackForm').addEventListener('click', goBack);
        $('btnRestart').addEventListener('click', function () {
            location.href = 'index.html';
        });
        $('resultUid').addEventListener('click', function () {
            var v = $('resultUid').textContent;
            if (!v || v === '—') return;
            if (navigator.clipboard) {
                navigator.clipboard.writeText(v).then(function () { toast('单号已复制'); });
            } else {
                toast('单号：' + v);
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bind();
        init();
    });
})();
