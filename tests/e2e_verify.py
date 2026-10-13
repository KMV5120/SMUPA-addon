# -*- coding: utf-8 -*-
"""
端到端集成测试（**平台侧单侧**）—— 管理员验收用。

与既有分层自检的分工：
    verify1  数据层（模型/占用语义/SQL 条数）
    verify2  平台端十个处理动作（逐个动作的正确性）
    verify4  对外接口契约（鉴权/校验/并发防重）
    mp_simulate.js / web_simulate.js  真 HTTP + CORS 传输层
    **verify_e2e（本文件）—— 把两侧串成一条完整业务链路**

本测试模拟两位真实用户，全程走 URL 路由 + 中间件 + 视图 + 表单 + 模型 + 数据库：

    ① 同学（匿名，同学侧自建页 / 小程序）
         看须知 -> 选座 -> 提交预约 -> 查我的预约 -> (事后)自助取消/改约
    ② 值班员（平台登录态，职务=主席）
         看到新单 -> 通过验证 -> 受理(指定引导员/时段/座位) -> 签到 -> 签退
         -> 发满意度调查 -> 分享码 -> 统计

关键断言不是"接口返回 200"，而是**跨侧一致性**：
    - 同学提交后，值班员平台的列表页里真的能看到这张单
    - 值班员受理后，同学侧查到的状态真的变成"接待未完成"
    - 值班员签退后，座位真的被释放、同学侧真的看到"已完成"
    - 中间任何一步的副产物（操作流水/统计计数/分享码）都对得上

**两处有意为之的测试替身**（已在报告里说明，不是绕过）：
    1. `send_email` 用桩替换 —— 平台发信走裸 smtplib（`utils/SMTP.py`），
       不受 Django `EMAIL_BACKEND` 控制；本地无真实 SMTP，真发必失败。
       桩捕获信件内容，反而能断言"收件人/主题/正文/链接"是否正确。
    2. `SURVEY_API_KEY` 未配置时先断言"拒绝访问"，再用 override_settings
       临时配置后断言数据能取出 —— 覆盖开关的两个方向。

全部数据包裹在事务里并回滚，可反复运行。
用法：./run.sh e2e
"""

import datetime
import hashlib
import json
import os
import re
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'local_settings')
django.setup()

from django.conf import settings  # noqa: E402
from django.db import transaction  # noqa: E402
from django.test import Client, override_settings  # noqa: E402

import web.views.meditation as meditation  # noqa: E402
from web import models  # noqa: E402
from web.meditation_constants import (  # noqa: E402
    MEDITATION_SEAT_NUMBERS,
    MEDITATION_SLOTS,
    format_res_datetime,
)

PASS, FAIL = [], []


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print('  OK   {}'.format(name))
    else:
        FAIL.append((name, got, want))
        print('  FAIL {}  期望={!r} 实际={!r}'.format(name, want, got))


def check_true(name, cond):
    check(name, bool(cond), True)


# ---------------------------------------------------------------------------
# 两位用户 / 两个客户端
# ---------------------------------------------------------------------------
CHAIR_CODE = '2021000001'   # 测试主席，user_type=6
STAFF_CODE = '2021000003'   # 测试干事，user_type=1（权限不足的样本）

# 日期取得足够远，避开"距开始不足 60 分钟不可自助改约"的时间门槛
DAY = datetime.date.today() + datetime.timedelta(days=30)
DAY2 = datetime.date.today() + datetime.timedelta(days=31)


def staff_client(stu_code=CHAIR_CODE):
    """值班员侧：带平台登录态（AuthMiddleware 认 session['user_id']）。"""
    c = Client()
    user = models.UserInfo.objects.get(stu_code=stu_code)
    s = c.session
    s['user_id'] = user.id
    s.save()
    return c, user


def token_for(openid):
    return hashlib.md5(
        '{}{}'.format(openid, settings.MEDITATION_API_KEY).encode('utf-8')).hexdigest()


def api(client, method, path, payload=None, openid=None):
    """同学侧对外接口。带 openid 时自动附 token（小程序路径）；不带即匿名（网页路径）。"""
    headers = {}
    if openid:
        headers['HTTP_X_MED_OPENID'] = openid
        headers['HTTP_X_MED_TOKEN'] = token_for(openid)
    if method == 'GET':
        r = client.get(path, **headers)
    else:
        r = client.post(path, data=json.dumps(payload or {}), content_type='application/json',
                        **headers)
    try:
        return r.status_code, json.loads(r.content.decode('utf-8'))
    except Exception:
        return r.status_code, {'_raw': r.content.decode('utf-8', 'ignore')[:300]}


def action(client, uid, method, **fields):
    """值班员侧：POST 到详情页，靠 method 字段分派动作。"""
    data = dict(fields)
    data['method'] = method
    r = client.post('/meditation/detail/{}/'.format(uid), data)
    try:
        return r.status_code, json.loads(r.content.decode('utf-8'))
    except Exception:
        return r.status_code, {'_raw': r.content.decode('utf-8', 'ignore')[:300]}


def submit_body(name, phone, slot, seat, **over):
    body = {
        'name': name, 'sex': 0, 'college': 2, 'grade': 2,
        'mobile_phone': phone, 'email': '{}@test.local'.format(phone),
        'res_date': str(DAY), 'slot': slot, 'seat': seat,
        'note': 'e2e 集成测试', 'agree': 1, 'read_seconds': 8,
    }
    body.update(over)
    return body


def form_of(uid):
    return models.Med_Form_Data.objects.get(res_form__uid=uid)


def ops(uid):
    return list(models.Med_Operation.objects.filter(ope_form__uid=uid)
                .order_by('id').values_list('operation', flat=True))


def page_has_uid(client, url, uid):
    """列表页正文里有没有**这张单**。

    ⚠️ 必须匹配 `<th>10</th>` 这种结构化片段，不能用 `'10' in html` 这种子串判断 ——
    页面里到处是日期与分页数字，"10" 会撞上 "2026-10-13" / "10:23" 之类，
    单号一变（比如从 15 变 10）结论就翻，是个假阳性陷阱。
    三个列表页共用 `meditation/_res_table.html`，单号渲染为 `<th>{{ item.uid }}</th>`。

    列表页按 `?search=<姓名>` 过滤到本测试的单，避免被分页挤到第 2 页。
    """
    r = client.get(url)
    html = r.content.decode('utf-8', 'ignore')
    return r.status_code, '<th>{}</th>'.format(uid) in html


# ===========================================================================
# 场景
# ===========================================================================
def s1_契约与初始状态(sc):
    print('\n[1] 同学侧进入：接口契约 + 初始占用为空')
    code, d = api(sc, 'GET', '/meditation/api/layout/')
    check('layout HTTP', code, 200)
    check_true('layout 返回成功', d.get('status'))
    data = d.get('data') or {}
    check('时段档数 = 11', len(data.get('slots') or []), len(MEDITATION_SLOTS))
    check('座位数 = 17', data.get('seat_count'), len(MEDITATION_SEAT_NUMBERS))
    check('冥想室 = 410B', data.get('meditation_room'), '410B')
    check('签到值班室 = 412', data.get('checkin_room'), '412')
    check_true('座位带 x/y 坐标（前端不硬编码）',
               all('x' in s and 'y' in s for s in (data.get('seats') or [])))
    check_true('下发门的位置', isinstance(data.get('door'), dict))
    check('改约提前量 = 60 分钟', data.get('reschedule_limit_minutes'), 60)
    check('现场签到提前量 = 5 分钟', data.get('min_ahead_minutes'), 5)
    check_true('随带选项（性别/学院/年级）',
               {'sex', 'college', 'grade'} <= set((data.get('choices') or {}).keys()))

    code, d = api(sc, 'GET', '/meditation/api/notice/')
    check_true('notice 返回成功', d.get('status'))
    notice = d.get('data') or {}
    check('须知最短阅读时长 = 5 秒', notice.get('min_read_seconds'), 5)
    check_true('须知含纸质签到说明', '值班室' in (notice.get('html') or ''))

    code, d = api(sc, 'GET', '/meditation/api/slots/?date={}'.format(DAY))
    check_true('slots 返回成功', d.get('status'))
    check('当日无任何占用', (d.get('data') or {}).get('taken'), [])
    check('per_slot 覆盖全部档位',
          len((d.get('data') or {}).get('per_slot') or []), len(MEDITATION_SLOTS))


def s2_小程序同学提交(sc):
    print('\n[2] 小程序同学提交预约 -> 落为「未验证」')
    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('集成甲同学', '13900001111', slot=2, seat=5),
                  openid='e2e-openid-jia')
    check('submit HTTP', code, 200)
    check_true('submit 返回成功', d.get('status'))
    uid = (d.get('data') or {}).get('uid')
    check_true('拿到单号', uid)
    check('提示含单号', '单号 {}'.format(uid) in (d.get('msg') or ''), True)

    check('状态 -> 未验证(5)', form_of(uid).status, 5)
    check('来源 -> 小程序(0)', models.Med_Reservation.objects.get(uid=uid).source, 0)
    check('openid 已绑定', models.Med_Reservation.objects.get(uid=uid).wx_openid,
          'e2e-openid-jia')
    check_true('座位被立刻占用（防双人约同座）',
               models.Med_Reservation.is_seat_taken(DAY, 2, 5))
    check('返回体带冥想室名', (d.get('data') or {}).get('meditation_room'), '410B')
    return uid


def s3_网页同学提交(sc):
    print('\n[3] 对外网页同学提交预约（必须完全无凭据也能用）')
    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('集成乙同学', '13900002222', slot=4, seat=8))
    check_true('匿名提交成功', d.get('status'))
    uid = (d.get('data') or {}).get('uid')
    check('来源 -> 对外网页(3)', models.Med_Reservation.objects.get(uid=uid).source, 3)
    check('未绑定 openid', models.Med_Reservation.objects.get(uid=uid).wx_openid, None)

    # 坏凭据不得静默降级为匿名：带了 token 但校验不过 -> 明确 401，且不落库。
    # 注意不能走 api()：它会为任何 openid 现算一个合法 token，测不出坏凭据。
    c = Client()
    body = json.dumps(submit_body('集成丙同学', '13900003333', slot=4, seat=9))
    r = c.post('/meditation/api/submit/', data=body, content_type='application/json',
               HTTP_X_MED_OPENID='evil', HTTP_X_MED_TOKEN='deadbeef')
    check('错 token HTTP 401', r.status_code, 401)
    check('错 token 未建单', models.Med_Reservation.objects.filter(
        mobile_phone='13900003333').count(), 0)
    return uid


def s4_提交负例(sc):
    print('\n[4] 同学侧提交负例：坏输入必须被拦')
    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('没同意同学', '13900004444', slot=6, seat=11, agree=0))
    check_true('未同意须知被拒', not d.get('status'))
    check_true('错误定位到 agree 字段', 'agree' in (d.get('error') or {}))

    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('没读够同学', '13900005555', slot=6, seat=11, read_seconds=1))
    check_true('阅读时长不足被拒', not d.get('status'))

    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('坐别人座同学', '13900006666', slot=2, seat=5))
    check_true('预约已被占座位被拒', not d.get('status'))
    check_true('错误定位到 seat 字段', 'seat' in (d.get('error') or {}))

    past = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('穿越同学', '13900007777', slot=6, seat=11, res_date=past))
    check_true('预约过去日期被拒', not d.get('status'))

    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('重复同学', '13900001111', slot=6, seat=11))
    check_true('同手机号重复预约被拒', not d.get('status'))
    check_true('提示指向先处理已有单', '正在处理中' in (d.get('msg') or ''))


def s5_值班员受理链路(staff, uid_jia):
    print('\n[5] 值班员侧：看到新单 -> 验证 -> 受理 -> 签到 -> 签退')
    # --- 平台列表页真的能看到这张单 ---
    code, has = page_has_uid(staff, '/meditation/list/?search=集成甲同学', uid_jia)
    check('平台「所有预约单」页可见该单', (code, has), (200, True))
    code, has = page_has_uid(staff, '/meditation/appoint/list/?search=集成甲同学', uid_jia)
    check('未验证单**不**出现在「待受理」页', has, False)

    # --- 通过验证：未验证(5) -> 待受理(0) ---
    code, d = action(staff, uid_jia, 'reg', staff1='')
    check_true('通过验证返回成功', d.get('status'))
    check('验证后状态 -> 待受理(0)', form_of(uid_jia).status, 0)
    check('写入操作流水 9（验证）', 9 in ops(uid_jia), True)
    code, has = page_has_uid(staff, '/meditation/appoint/list/?search=集成甲同学', uid_jia)
    check('验证后出现在「待受理」页', has, True)

    # --- 受理：待受理(0) -> 接待未完成(1) ---
    code, d = action(staff, uid_jia, 'reservation', guide='值班张三',
                     res_date=str(DAY), slot=2, seat=5, staff='测试部长')
    check_true('受理返回成功', d.get('status'))
    f = form_of(uid_jia)
    check('受理后状态 -> 接待未完成(1)', f.status, 1)
    check('引导员已落库', f.guide, '值班张三')
    check('预约时间串已生成', f.res_datetime, format_res_datetime(DAY, 2))
    check('写入操作流水 2（受理）', 2 in ops(uid_jia), True)
    code, has = page_has_uid(staff, '/meditation/receive/list/?search=集成甲同学', uid_jia)
    check('受理后出现在「待到访」页', has, True)

    # --- 签到 ---
    code, d = action(staff, uid_jia, 'checkin', staff='')
    check_true('签到返回成功', d.get('status'))
    check_true('签到时间已写',
               models.Med_Reservation.objects.get(uid=uid_jia).checkin_datetime is not None)
    check('写入操作流水 4（签到）', 4 in ops(uid_jia), True)

    # --- 签退 ---
    code, d = action(staff, uid_jia, 'finish', staff='测试部长')
    check_true('签退返回成功', d.get('status'))
    check('签退后状态 -> 已完成(2)', form_of(uid_jia).status, 2)
    check_true('签退时间已写',
               models.Med_Reservation.objects.get(uid=uid_jia).checkout_datetime is not None)
    check('写入操作流水 11（签退）', 11 in ops(uid_jia), True)
    check('签退提示含接待者', '接待者' in (d.get('msg') or ''), True)
    check('签退后座位被释放', models.Med_Reservation.is_seat_taken(DAY, 2, 5), False)


def s6_受理冲突负例(staff, uid_yi):
    print('\n[6] 值班员侧负例：受理到已被占用的座位必须被拒')
    # 造一张第三方「已受理」（status=1，占用中）的单作为冲突源。
    # 甲同学那张此刻已签退(2)、座位已释放，不能拿来当冲突源。
    blocker = models.Med_Reservation.objects.create(
        uid=90001, name='占位同学', sex=0, college=0, grade=2,
        mobile_phone='13911110000', res_date=DAY, slot=3, seat=7,
        note='e2e 冲突源', agree=1, source=0,
    )
    models.Med_Form_Data.objects.create(res_form=blocker, status=1)
    check_true('前置：目标座位当前被占', models.Med_Reservation.is_seat_taken(DAY, 3, 7))

    action(staff, uid_yi, 'reg', staff1='')
    check('乙同学验证后 -> 待受理(0)', form_of(uid_yi).status, 0)
    code, d = action(staff, uid_yi, 'reservation', guide='', res_date=str(DAY),
                     slot=3, seat=7, staff='')
    check_true('受理到已占座位被拒', not d.get('status'))
    check_true('错误定位到 seat 字段', 'seat' in (d.get('error') or {}))
    check('被拒后状态未被改动', form_of(uid_yi).status, 0)


def s7_状态回流到同学侧(sc, uid_jia, uid_yi):
    print('\n[7] 状态回流：同学侧看到的值与平台侧一致')
    code, d = api(sc, 'POST', '/meditation/api/mpl/list/',
                  {'mobile_phone': '13900001111', 'openid': 'e2e-openid-jia',
                   'token': token_for('e2e-openid-jia')})
    check_true('mpl/list 返回成功', d.get('status'))
    items = {i['uid']: i for i in (d.get('data') or {}).get('list', [])}
    check('能查到自己的单', uid_jia in items, True)
    check('同学侧状态 = 2（已完成）', items[uid_jia]['status'], 2)
    check('同学侧状态文案', items[uid_jia]['status_display'], '已完成')
    check_true('同学侧看得到签到时间', bool(items[uid_jia]['checkin_datetime']))
    check('已完成单不可再自助取消', items[uid_jia]['can_cancel'], False)

    code, d = api(sc, 'GET', '/meditation/api/slots/?date={}'.format(DAY))
    taken = (d.get('data') or {}).get('taken') or []
    check('已释放的座位不在占用列表', [2, 5] in taken, False)
    check('乙同学未受理的座位仍在占用列表', [4, 8] in taken, True)


def s8_问卷闭环(staff, uid_jia, mailbox):
    print('\n[8] 满意度调查闭环（邮件桩 + 匿名公开页 + 数据接口）')
    f = form_of(uid_jia)
    check('前置：本单已签退(2)', f.status, 2)

    r = staff.get('/meditation/send/survey/{}/'.format(f.res_form_id))
    d = json.loads(r.content.decode('utf-8'))
    check_true('发放调查邀请成功', d.get('status'))
    check('桩确实收到一封信', len(mailbox), 1)
    if mailbox:
        letter = mailbox[0]
        check('收件人 = 预约人邮箱', letter['to'], '13900001111@test.local')
        check('主题正确', letter['subject'], 'SMUPA冥想室体验反馈邀请')
        check('正文用 HTML', letter['type'], 'html')
        check_true('正文含预约时间', format_res_datetime(DAY, 2) in letter['content'])
        check_true('正文含评价链接', '/meditation/survey/' in letter['content'])

    f.refresh_from_db()
    check('调查邀请标记 invited', f.invited, True)
    check_true('生成校验码 survey_code', bool(f.survey_code))

    r = staff.get('/meditation/send/survey/{}/'.format(f.res_form_id))
    d = json.loads(r.content.decode('utf-8'))
    check_true('重复发送被拒', not d.get('status'))
    check_true('提示勿重复', '重复' in (d.get('msg') or ''))

    # ↓ 同学是**从邮件里点链接**进来的 —— 无任何登录态，必须能开
    guest = Client()
    r = guest.get('/meditation/survey/{}/wrongcode/'.format(f.res_form_id))
    check('错 code 未登录可访问（不是被登录页拦掉）', r.status_code, 200)
    check('错 code 报校验失败',
          '校验失败' in r.content.decode('utf-8', 'ignore'), True)

    r = guest.get('/meditation/survey/{}/{}/'.format(f.res_form_id, f.survey_code))
    html = r.content.decode('utf-8', 'ignore')
    check('正确 code 匿名可开问卷', r.status_code, 200)
    check('问卷页含全部题目', all('question{}'.format(i) in html for i in range(1, 6)), True)
    check('正确 code 不报校验失败', '校验失败' in html, False)

    r = guest.post('/meditation/survey/{}/{}/'.format(f.res_form_id, f.survey_code),
                   {'question1': 5, 'question2': 4, 'question3': 5,
                    'question4': 4, 'question5': '环境很安静，体验很好'})
    d = json.loads(r.content.decode('utf-8'))
    check_true('匿名提交问卷成功', d.get('status'))
    f.refresh_from_db()
    check('问卷完成标记', f.is_survey_completed, True)
    check_true('问卷答案已落库', bool(f.survey_data))
    check('答案是原样留存（未加工）', json.loads(f.survey_data).get('question1'), ['5'])
    check('自由文本也留存', json.loads(f.survey_data).get('question5'), ['环境很安静，体验很好'])

    # 越界分值应被问卷表单拦下
    f.is_survey_completed = False
    f.save(update_fields=['is_survey_completed'])
    r = guest.post('/meditation/survey/{}/{}/'.format(f.res_form_id, f.survey_code),
                   {'question1': 9, 'question2': 4, 'question3': 5, 'question4': 4})
    check_true('分值越界被拒', not json.loads(r.content.decode('utf-8')).get('status'))
    f.is_survey_completed = True
    f.save(update_fields=['is_survey_completed'])

    r = guest.get('/meditation/survey/{}/{}/'.format(f.res_form_id, f.survey_code))
    check('已完成后再打开被拒',
          '已完成' in r.content.decode('utf-8', 'ignore'), True)

    # 数据接口：未配置 key 一律拒绝（不留后门）
    r = staff.get('/meditation/api/survey/data/e2ekey/')
    check('未配置 SURVEY_API_KEY 时拒绝', json.loads(r.content.decode('utf-8')).get('code'), 401)

    # key 里带连字符会 404：路由是 (?P<key>\w+)，\w 不含 '-'。
    # 这与平台原有心理预约的 /api/survey/data/<key>/ 同款，属继承的既有约定，
    # 不是本模块引入 —— 但管理员配 SURVEY_API_KEY 时须避免连字符。
    r = staff.get('/meditation/api/survey/data/e2e-key/')
    check('key 含连字符会 404（既有约定，配 key 时避开）', r.status_code, 404)

    with override_settings(SURVEY_API_KEY='e2ekey'):
        r = staff.get('/meditation/api/survey/data/e2ekey/')
        d = json.loads(r.content.decode('utf-8'))
        check('配好 key 后取数成功', d.get('code'), 200)
        mine = [x for x in d.get('data', []) if x.get('res_id') == uid_jia]
        check('数据里含本单', len(mine), 1)
        if mine:
            check('数据里含引导员', mine[0].get('guide'), '值班张三')
            # 注意：survey_data 存的是 dict(request.POST)，值是**列表**；
            # 对外接口原样摊平，故取值也是列表。与平台原有心理预约同款。
            check('数据里含问卷答案', mine[0].get('question5'), ['环境很安静，体验很好'])


def s9_统计流水分享打印(staff, uid_jia):
    print('\n[9] 值班员侧：操作流水 / 统计 / 分享码 / 打印')
    r = staff.get('/meditation/api/history/')
    d = json.loads(r.content.decode('utf-8'))
    check_true('操作历史接口成功', d.get('status'))
    mine = [x for x in d.get('data', []) if x.get('uid') == uid_jia]
    seen = sorted({x['operation'] for x in mine})
    check('流水含 2/4/9/11', set([2, 4, 9, 11]) <= set(seen), True)
    check_true('流水带操作者', all(x.get('operator') for x in mine))

    r = staff.get('/meditation/api/check/statistics')
    d = json.loads(r.content.decode('utf-8'))
    check_true('统计接口成功', d.get('status'))
    stat = {x['name']: x['num'] for x in d.get('data', [])}
    check_true('今日受理数 >= 1', stat.get('reception-today', 0) >= 1)
    check_true('今日签到数 >= 1', stat.get('appointment-today', 0) >= 1)

    # 分享码：值班员生成，被分享者（未登录）打开
    r = staff.post('/meditation/share/code/{}/'.format(
        models.Med_Reservation.objects.get(uid=uid_jia).id),
        {'period': 60, 'count': 2})
    d = json.loads(r.content.decode('utf-8'))
    check_true('生成分享码成功', d.get('status'))
    url = (d.get('data') or '')
    check_true('返回分享链接', '/meditation/share/visit/' in url)
    if '/meditation/share/visit/' in url:
        path = '/' + url.split('/', 3)[3]
        guest = Client()
        r = guest.get(path)
        check('分享链接匿名可访问', r.status_code, 200)
        share = models.Med_Share.objects.filter(consult__uid=uid_jia).first()
        check('分享码访问次数已计', share.use_count, 1)
        check('分享链接不泄露他人数据', '13900002222' in r.content.decode('utf-8', 'ignore'), False)

    r = staff.get('/meditation/print/{}/'.format(uid_jia))
    check('打印页 HTTP', r.status_code, 200)


def s10_同学自助取消改约(sc, staff):
    print('\n[10] 同学自助取消 / 改约（含归属校验）')
    # 造一张待受理的单（值班主任代录，避免与同学侧重复校验打架）
    code, d = api(sc, 'POST', '/meditation/api/submit/',
                  submit_body('自助同学', '13900008888', slot=8, seat=14))
    check_true('建单成功', d.get('status'))
    uid = d['data']['uid']
    check_true('座位已占用', models.Med_Reservation.is_seat_taken(DAY, 8, 14))

    # 手机号不符 -> 拒绝
    code, d = api(sc, 'POST', '/meditation/api/cancel/',
                  {'uid': uid, 'mobile_phone': '13000000000'})
    check_true('手机号不符被拒', not d.get('status'))

    # 改约：换到新座位，旧座释放
    code, d = api(sc, 'POST', '/meditation/api/reschedule/',
                  {'uid': uid, 'mobile_phone': '13900008888',
                   'res_date': str(DAY2), 'slot': 9, 'seat': 15})
    check_true('改约成功', d.get('status'))
    r = models.Med_Reservation.objects.get(uid=uid)
    check('改后日期', str(r.res_date), str(DAY2))
    check('改后时段', r.slot, 9)
    check('改后座位', r.seat, 15)
    check('旧座位已释放', models.Med_Reservation.is_seat_taken(DAY, 8, 14), False)
    check_true('新座位已占用', models.Med_Reservation.is_seat_taken(DAY2, 9, 15))

    # 取消
    code, d = api(sc, 'POST', '/meditation/api/cancel/',
                  {'uid': uid, 'mobile_phone': '13900008888'})
    check_true('取消成功', d.get('status'))
    check('取消后状态 -> 作废(3)', form_of(uid).status, 3)
    check('取消后座位释放', models.Med_Reservation.is_seat_taken(DAY2, 9, 15), False)
    check_true('取消写进备注', '自行取消' in (form_of(uid).comment or ''))

    # 已作废的单不能再改约
    code, d = api(sc, 'POST', '/meditation/api/reschedule/',
                  {'uid': uid, 'mobile_phone': '13900008888',
                   'res_date': str(DAY), 'slot': 1, 'seat': 1})
    check_true('已作废单不可再改约', not d.get('status'))


def s11_权限门槛(uid_jia):
    print('\n[11] 权限门槛：低职务不得发调查邀请')
    staff_low, _ = staff_client(STAFF_CODE)
    r = staff_low.get('/meditation/send/survey/{}/'.format(uid_jia))
    d = json.loads(r.content.decode('utf-8'))
    check_true('干事发调查被拒', not d.get('status'))
    check('提示权限不足', d.get('msg'), '权限不足！')


def s12_模块隔离(uid_jia, psy_ops_before):
    print('\n[12] 模块隔离：冥想室链路绝不污染心理预约的数据')
    check('心理预约 Operation 表条数未变',
          models.Operation.objects.count(), psy_ops_before)
    check_true('冥想室 Med_Operation 表确实有本单流水', len(ops(uid_jia)) >= 4)
    check_true('平台既有心理预约单仍存在',
               models.Reservation.objects.exists())


def s13_咨询预约周历(staff):
    """本次新增的平台侧改动：咨询预约栅格周历 + 首页区块改名与按钮。

    与冥想室无关，是给平台原有咨询预约模块加的一页；放这里一起回归，
    是因为它同样属于「平台侧交付物」，且共用了首页。
    """
    print('\n[13] 咨询预约周历（本次新增）与首页区块')

    # --- 首页：两块并存、标题可区分、按钮对称 ---
    r = staff.get('/dashboard/')
    html = r.content.decode('utf-8', 'ignore')
    check('首页 HTTP', r.status_code, 200)
    check('存在「咨询预约处理」区块标题', '咨询预约处理' in html, True)
    check('存在「冥想室预约处理」区块标题', '冥想室预约处理' in html, True)
    check('旧标题「预约处理」已不再单独出现（已改名）',
          '<h3 class="mb-5">预约处理</h3>' in html, False)
    check('咨询预约区块有「预约周历」按钮',
          '/consultation/calendar/' in html, True)
    check('咨询预约区块有「预约填写」按钮', '/new/reservation/' in html, True)
    check('咨询预约区块有「操作历史」按钮', '/operate/history/' in html, True)

    # --- 新周历页本身 ---
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.isoweekday() - 1)
    wednesday = monday + datetime.timedelta(days=2)

    r = staff.get('/consultation/calendar/')
    html = r.content.decode('utf-8', 'ignore')
    check('新周历 HTTP', r.status_code, 200)
    check('新周历用了栅格样式', 'res-calendar' in html, True)
    check('新周历含小时行首', '07:00 - 08:00' in html, True)
    check('新周历含小时行尾', '20:00 - 21:00' in html, True)
    check('新周历含本周日期区间',
          monday.strftime('%Y-%m-%d') in html and (monday + datetime.timedelta(days=6)).strftime('%Y-%m-%d') in html,
          True)

    # --- 造一条本周三的咨询单，应出现在周历里 ---
    res = models.Reservation.objects.create(
        uid=88001, name='周历同学', sex=0, college=0, grade=2,
        mobile_phone='13700008888', abstract='e2e 周历用例',
        expect_sex=2, expect_age=3, expect_time='工作日下午', agree=1)
    models.Res_Form_Data.objects.create(
        res_form=res, status=0, filler=None,
        res_datetime='{} 10:30'.format(wednesday), psychologist='王老师')

    r = staff.get('/consultation/calendar/')
    html = r.content.decode('utf-8', 'ignore')
    check('本周的单出现在周历里', '88001' in html, True)
    check('周历显示咨询师', '王老师' in html, True)
    check('周历显示具体时刻', '10:30' in html, True)

    # --- 已完成(2)的单不该出现在周历（与冥想室同口径：只看 0/1）---
    models.Res_Form_Data.objects.filter(res_form=res).update(status=2)
    r = staff.get('/consultation/calendar/')
    check('已完成单不进周历',
          '88001' in r.content.decode('utf-8', 'ignore'), False)

    # --- 坏数据：不该拖垮整页（原有 /calendar/ 会整页变错误页）---
    bad = models.Reservation.objects.create(
        uid=88002, name='脏数据同学', sex=0, college=0, grade=2,
        mobile_phone='13700009999', abstract='e2e 坏时间',
        expect_sex=2, expect_age=3, expect_time='工作日下午', agree=1)
    models.Res_Form_Data.objects.create(
        res_form=bad, status=1, filler=None, res_datetime='格式坏了')

    r = staff.get('/consultation/calendar/')
    html = r.content.decode('utf-8', 'ignore')
    check('坏数据时新周历仍正常渲染', r.status_code, 200)
    check('坏数据时仍出栅格', 'res-calendar' in html, True)
    check('坏数据被明确提示跳过', '格式不合法' in html, True)

    r = staff.get('/calendar/')
    check('原有 /calendar/ 未被改动仍可达', r.status_code, 200)
    check('原有 /calendar/ 对坏数据仍是整页错误页（既有行为，未动它）',
          '日期格式错误' in r.content.decode('utf-8', 'ignore'), True)


def s14_CSRF(staff):
    """回归：详情页的动作在**真实浏览器**里点得动吗。

    为什么必须单独测：Django 测试客户端默认 `enforce_csrf_checks=False`
    —— 整个 CSRF 校验被绕过。所以即使模板里漏了 `{% csrf_token %}`
    （真实浏览器里所有处理按钮都会 403），前面 13 组也会**全绿**。
    这里显式打开校验再走一遍，把这条盲区堵上。

    背景：`detail_meditation.html` 曾一度 11 个 form 一个 token 都没有，
    而咨询预约的 `detail_reservation.html` 每个 form 都有 —— 属照搬时的遗漏。
    """
    print('\n[14] CSRF：详情页动作在真实浏览器里点得动吗')

    uid = 96001
    res = models.Med_Reservation.objects.create(
        uid=uid, name='CSRF 回归样本', sex=0, college=0, grade=2,
        mobile_phone='13900096001', email='csrf@test.local',
        res_date=DAY, slot=7, seat=9, note='', agree=1, source=3,
    )
    models.Med_Form_Data.objects.create(res_form=res, status=5)

    strict = Client(enforce_csrf_checks=True)
    u = models.UserInfo.objects.get(stu_code=CHAIR_CODE)
    s = strict.session
    s['user_id'] = u.id
    s.save()

    url = '/meditation/detail/{}/'.format(uid)

    # ① 不带 token 的 POST 必须被拒（证明 CSRF 真的是开着的，测试没自欺）
    r = strict.post(url, {'method': 'reg', 'staff1': ''})
    check('不带 CSRF token 的 POST 被拒', r.status_code, 403)

    # ② 先 GET：模板里有 {% csrf_token %} 才会下发 csrftoken cookie
    r = strict.get(url)
    check('详情页 GET 正常', r.status_code, 200)
    check_true('GET 下发了 csrftoken cookie', 'csrftoken' in strict.cookies)
    token = strict.cookies['csrftoken'].value if 'csrftoken' in strict.cookies else ''
    check_true('拿到 csrftoken', bool(token))

    # ③ 带上 token（浏览器 AJAX 会把表单里的 hidden input 一起 serialize 上来）
    r = strict.post(url, {'method': 'reg', 'staff1': '',
                          'csrfmiddlewaretoken': token})
    check('带 CSRF token 的 POST 成功', r.status_code, 200)
    check('状态 5 -> 0', form_of(uid).status, 0)

    # ④ 模板级兜底：每个 <form> 后面都必须是 {% csrf_token %}，
    #    防止以后新增表单时又漏掉。这比逐个动作去试更彻底。
    tpl_path = os.path.join(settings.BASE_DIR, 'web', 'templates',
                            'meditation', 'detail_meditation.html')
    with open(tpl_path, encoding='utf-8') as f:
        tpl = f.read()
    forms = re.findall(r'<form[^>]*>\s*(\{%\s*csrf_token\s*%\})?', tpl)
    missing = sum(1 for g in forms if not g)
    check('模板里 form 总数 > 0（确认真的读到了模板）', len(forms) > 0, True)
    check('每个 form 都带 csrf_token（缺 {} 个）'.format(missing), missing, 0)


def main():
    print('=' * 68)
    print('平台侧 —— 端到端集成测试')
    print('（主线：冥想室预约全链路；另含本次新增的咨询预约周历）')
    print('=' * 68)

    mailbox = []
    real_send_email = meditation.send_email

    def fake_send_email(email, title, content, send_type='text'):
        mailbox.append({'to': email, 'subject': title, 'content': content, 'type': send_type})
        return {'code': 0, 'message': 'stubbed', 'data': {}}

    meditation.send_email = fake_send_email
    try:
        with transaction.atomic():
            psy_ops_before = models.Operation.objects.count()
            sc = Client()                       # 同学侧：匿名
            staff, _chair = staff_client()      # 值班员侧：登录态

            # 顺序要紧：s1 断言"当日无任何占用"，必须在任何写入之前跑
            s1_契约与初始状态(sc)
            uid_jia = s2_小程序同学提交(sc)
            uid_yi = s3_网页同学提交(sc)
            s4_提交负例(sc)
            s5_值班员受理链路(staff, uid_jia)
            s6_受理冲突负例(staff, uid_yi)
            s7_状态回流到同学侧(sc, uid_jia, uid_yi)
            s8_问卷闭环(staff, uid_jia, mailbox)
            s9_统计流水分享打印(staff, uid_jia)
            s10_同学自助取消改约(sc, staff)
            s11_权限门槛(uid_jia)
            s12_模块隔离(uid_jia, psy_ops_before)
            s13_咨询预约周历(staff)
            s14_CSRF(staff)

            transaction.set_rollback(True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAIL.append(('脚本异常', str(e), '无异常'))
    finally:
        meditation.send_email = real_send_email

    print('\n' + '=' * 68)
    print('通过 {} 项，失败 {} 项'.format(len(PASS), len(FAIL)))
    for name, got, want in FAIL:
        print('  FAIL {}  期望={!r} 实际={!r}'.format(name, want, got))
    print('（数据已回滚）')
    print('=' * 68)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
