# -*- coding: utf-8 -*-
"""
冥想室 —— 微信小程序接口

设计要点
--------
1. 全部 `@csrf_exempt`：小程序请求不带 Cookie，靠**签名 token** 鉴权，
   而不是 CSRF。这些路径已加入 settings.WHITE_REGEX_URL_LIST。
2. **不引用 request.STAFF.user**：小程序用户不是平台成员，中间件会把它
   拦到内存页；这些视图完全走自己的身份体系（wx_openid）。
3. 鉴权用 bearer token：`token = md5(openid + MEDITATION_API_KEY)`，
   由 wxlogin 下发、后续请求带 X-Med-Token 与 X-Med-Openid。
   AppSecret 只留在服务器，绝不下发。
4. 写操作全部包在事务里并**在事务内复查座位**，与平台端口径一致。

响应统一为：{"status": bool, "data": {...}, "error": {...}, "msg": "..."}
"""

import datetime
import hashlib
import hmac
import json

import requests
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from utils.wx_pusher import send_pusher_by_id
from utils.validate_tools import parse_date
from web import models
from web.meditation_constants import (
    MEDITATION_SLOTS,
    MEDITATION_SEAT_NUMBERS,
    MEDITATION_NOTICE_MIN_READ_SECONDS,
    MEDITATION_RESCHEDULE_LIMIT_MINUTES,
    MEDITATION_MIN_AHEAD_MINUTES,
    MEDITATION_MAX_USE_MINUTES,
    slot_label,
    format_res_datetime,
    as_json,
)

WX_LOGIN_URL = 'https://api.weixin.qq.com/sns/jscode2session'


# ===========================================================================
# 通用工具
# ===========================================================================
def _ok(data=None, msg=''):
    return JsonResponse({'status': True, 'data': data or {}, 'msg': msg})


def _err(msg, error=None, http=200):
    return JsonResponse({'status': False, 'data': {}, 'error': error or {}, 'msg': msg},
                        status=http)


def _payload(request):
    """取请求参数，兼容 JSON body 与表单两种形式。

    小程序默认发 application/json，但也允许 form 编码（便于 curl 调试）。
    """
    raw = request.body or b''
    if raw:
        try:
            data = json.loads(raw.decode('utf-8'))
            if isinstance(data, dict):
                return data
        except (ValueError, UnicodeDecodeError):
            pass
    return request.POST.dict()


def _make_token(openid):
    """下发/校验用的 bearer token。刻意用裸 md5（不含 SECRET_KEY），
    这样服务端与校验端算法完全一致、无需共享 SECRET_KEY。"""
    return hashlib.md5('{}{}'.format(openid, settings.MEDITATION_API_KEY).encode('utf-8')).hexdigest()


def _auth(request, payload):
    """校验微信小程序身份，返回 openid；失败返回 None。

    token 走 header 优先、body 兜底；比较用 hmac.compare_digest 防时序侧信道。
    """
    openid = request.META.get('HTTP_X_MED_OPENID') or payload.get('openid') or ''
    token = request.META.get('HTTP_X_MED_TOKEN') or payload.get('token') or ''
    if not openid or not token or not settings.MEDITATION_API_KEY:
        return None
    if not hmac.compare_digest(_make_token(openid), str(token)):
        return None
    return openid


def _resolve_identity(request, payload):
    """解析请求身份，返回 (openid, error_response)。

    规则（重要）：
      - **完全没带** token/openid  → 视为对外网页的匿名请求，openid=None，放行
      - **带了但校验不过**        → 直接拒绝

    第二条是为了避免"凭据失效被静默降级成匿名"：小程序若持有过期/错误的 token，
    应当得到明确报错并重新登录，而不是悄悄以匿名身份继续操作。
    """
    token = request.META.get('HTTP_X_MED_TOKEN') or payload.get('token') or ''
    openid_in = request.META.get('HTTP_X_MED_OPENID') or payload.get('openid') or ''
    if not token and not openid_in:
        return None, None
    openid = _auth(request, payload)
    if openid is None:
        return None, _err('身份校验失败，请重新进入小程序', http=401)
    return openid, None


def _owns(res_obj, openid, mobile_phone):
    """判断请求方是否有权操作某张单。

    两条合法路径（对应两个入口）：
      1. 微信小程序：openid 与该单的 wx_openid 一致（强归属）
      2. 对外网页：未登录，凭预约时填写的**手机号**认领（弱归属）

    网页路径是弱校验 —— 知道手机号的人即可改约/取消。这是与委托人确认过的
    取舍：校园场景下比"必须登录"的现实成本低得多。要收紧只需在此处加短信验证码。
    """
    if openid and res_obj.wx_openid and hmac.compare_digest(str(res_obj.wx_openid), str(openid)):
        return True
    if mobile_phone and res_obj.mobile_phone == str(mobile_phone).strip():
        return True
    return False


def _meditation_room():
    """冥想室本身（同学实际使用的地方）。"""
    from web.meditation_constants import MEDITATION_ROOM_DEFAULT
    return getattr(settings, 'MEDITATION_ROOM', '') or MEDITATION_ROOM_DEFAULT


def _checkin_room():
    """签到 / 签退值班室（纸质签到在这里）。

    与冥想室是两个不同的地方，响应里分别给 meditation_room / checkin_room，
    前端按语境取用，不要混。
    """
    from web.meditation_constants import MEDITATION_CHECKIN_ROOM_DEFAULT
    return (getattr(settings, 'MEDITATION_CHECKIN_ROOM', '')
            or MEDITATION_CHECKIN_ROOM_DEFAULT)


def _validate_submission(payload):
    """校验提交内容，返回 (cleaned, error_dict)。"""
    err = {}
    name = (payload.get('name') or '').strip()
    if not name:
        err['name'] = '请填写姓名'
    mobile = (payload.get('mobile_phone') or '').strip()
    if not mobile:
        err['mobile_phone'] = '请填写手机号'

    res_date = parse_date(str(payload.get('res_date') or ''))
    if res_date is None:
        err['res_date'] = '日期格式不合法（应为 YYYY-MM-DD）'
    elif res_date < datetime.date.today():
        err['res_date'] = '不能预约过去的日期'

    try:
        slot = int(payload.get('slot'))
    except (TypeError, ValueError):
        slot = None
    if slot not in dict(MEDITATION_SLOTS):
        err['slot'] = '请选择时段'

    try:
        seat = int(payload.get('seat'))
    except (TypeError, ValueError):
        seat = None
    if seat not in MEDITATION_SEAT_NUMBERS:
        err['seat'] = '请选择座位'

    # 须先阅读《须知与承诺》
    try:
        read_seconds = int(payload.get('read_seconds') or 0)
    except (TypeError, ValueError):
        read_seconds = 0
    if not payload.get('agree'):
        err['agree'] = '请先阅读并同意《须知与承诺》'
    elif read_seconds < MEDITATION_NOTICE_MIN_READ_SECONDS:
        err['agree'] = '阅读《须知与承诺》时长不足，请仔细阅读后再提交'

    if err:
        return None, err

    cleaned = {
        'name': name,
        'mobile_phone': mobile,
        'res_date': res_date,
        'slot': slot,
        'seat': seat,
        'read_seconds': read_seconds,
        'sex': int(payload.get('sex') or 0),
        'college': int(payload.get('college') or 10),
        'grade': int(payload.get('grade') or 9),
        'stu_code': (payload.get('stu_code') or '').strip() or None,
        'email': (payload.get('email') or '').strip() or None,
        'note': (payload.get('note') or '').strip(),
        'agree': 1,
    }
    return cleaned, None


def _slot_start_dt(res_date, slot):
    """把 (日期, 时段档) 还原成该档的**起始时间**，用于"提前 N 分钟"类校验。

    时段表里存的是 '8:20-9:00' 这种区间文本，不能直接 strptime；
    起止时间已单独拆在 MEDITATION_SLOT_START / MEDITATION_SLOT_END。
    """
    from web.meditation_constants import MEDITATION_SLOT_START
    hhmm = MEDITATION_SLOT_START.get(slot)
    if not hhmm or not res_date:
        return None
    return datetime.datetime.strptime('{} {}'.format(res_date, hhmm), '%Y-%m-%d %H:%M')


def _next_uid():
    last = models.Med_Reservation.objects.order_by('-uid').first()
    return (last.uid + 1) if last else 1


def _client_ip(request):
    return (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR') or '')


def _throttle(request, action, limit, window_seconds):
    """按 IP 限流。返回 True 表示放行，False 表示超限。

    对外预约页是免登录的，没有这道闸门任何人都能脚本刷单。
    用 Django cache 计数；cache 不可用时**放行**（宁可漏拦，不可误拦正常用户）。

    ⚠️ 校园网 NAT：整个校园往往共用少数几个公网出口 IP，
    因此阈值必须**按"一个出口 IP 可能代表成百上千人"来定**，
    不能按"每人一个 IP"来想 —— 定小了会把正常同学误拦。
    阈值可在 settings 里配，或在 .env 里改；设为 0 表示关闭该限流。
    """
    limit = int(limit or 0)
    if limit <= 0:
        return True
    from django.core.cache import cache
    ip = _client_ip(request)
    if not ip:
        return True
    key = 'med_throttle:{}:{}'.format(action, ip)
    try:
        if cache.add(key, 1, window_seconds):
            return True
        count = cache.incr(key)
        return count <= limit
    except Exception:
        return True


def _append_comment(res_form, text):
    """小程序用户没有平台账号，无法写操作流水（operator 是必填外键），
    因此把用户侧动作以带标记的文字追加到处理备注里，值班员在详情页可见。"""
    stamped = '【小程序】{}'.format(text)
    res_form.comment = (res_form.comment + ' || ' + stamped) if res_form.comment else stamped
    res_form.save(update_fields=['comment'])


# ===========================================================================
# 接口
# ===========================================================================
@csrf_exempt
def wx_login(request):
    """POST {"code": "wx.login 返回的 code"} -> {"openid": ..., "token": ...}

    服务端拿 code + AppSecret 去微信换 openid；AppSecret 不下发。
    未配置小程序凭据时直接返回明确错误，不做任何"开发模式后门"。
    """
    if request.method != 'POST':
        return _err('不支持的请求方式', http=405)
    if not settings.MEDITATION_MINIPROGRAM_APPID or not settings.MEDITATION_MINIPROGRAM_SECRET:
        return _err('小程序未配置（缺少 AppID / AppSecret），无法登录')

    payload = _payload(request)
    code = (payload.get('code') or '').strip()
    if not code:
        return _err('缺少 code 参数')

    try:
        resp = requests.get(WX_LOGIN_URL, params={
            'appid': settings.MEDITATION_MINIPROGRAM_APPID,
            'secret': settings.MEDITATION_MINIPROGRAM_SECRET,
            'js_code': code,
            'grant_type': 'authorization_code',
        }, timeout=8)
        data = resp.json()
    except Exception as e:
        return _err('调用微信接口失败：{}'.format(e))

    openid = data.get('openid')
    if not openid:
        return _err('微信登录失败：{}'.format(data.get('errmsg') or data))

    return _ok({'openid': openid, 'token': _make_token(openid)})


def layout(request):
    """GET -> 时段表 + 座位坐标 + 门 + 阈值。

    平台端与小程序端共用这一份数据，从根本上杜绝两端座位图画歪。
    """
    if request.method != 'GET':
        return _err('不支持的请求方式', http=405)
    data = as_json()
    # as_json 已带默认房间名，这里用 settings 覆盖（如已配置）
    data['meditation_room'] = _meditation_room()
    data['checkin_room'] = _checkin_room()
    # 把选项一并下发，前端无需再抄一份（避免与 models.py 的 choices 分叉）
    data['choices'] = {
        'sex': [[k, v] for k, v in models.Reservation.sex_choice],
        'college': [[k, v] for k, v in models.college_choice],
        'grade': [[k, v] for k, v in models.Reservation.grade_choice],
    }
    return _ok(data)


def notice(request):
    """GET -> 《须知与承诺》正文与最短阅读时长。"""
    if request.method != 'GET':
        return _err('不支持的请求方式', http=405)

    html = (getattr(settings, 'MEDITATION_NOTICE_HTML', '') or '').strip()
    if not html:
        # 默认文案取自《冥想室使用流程与相关注意事项》
        html = (
            '<p>欢迎使用心理协会冥想室。请先阅读以下须知，阅读满 '
            '{} 秒后方可进入下一步。</p>'
            '<p><strong>一、预约与到场</strong></p>'
            '<ul>'
            '<li>预约成功后系统生成唯一单号，请牢记以便查验。</li>'
            '<li>单次使用时长以所选时段为准（每档 {} 分钟）。</li>'
            '<li>请至少提前 {} 分钟到 {} 值班室现场纸质签到，由值班员引导进入 {} 冥想室。</li>'
            '<li>需改约或取消的，请至少提前 {} 分钟操作。</li>'
            '</ul>'
            '<p><strong>二、环境卫生</strong></p>'
            '<ul>'
            '<li>严禁携带带有刺激性气味的食物、有色饮料进入冥想室。</li>'
            '<li>随身物品可寄存于值班室，请勿堆放在冥想室内。</li>'
            '</ul>'
            '<p><strong>三、秩序纪律</strong></p>'
            '<ul>'
            '<li>室内请保持安静，尊重他人的冥想体验。</li>'
            '<li>不得进行与冥想、放松无关的活动。</li>'
            '</ul>'
            '<p><strong>四、安全与设备</strong></p>'
            '<ul>'
            '<li>请按值班员指引使用设备，勿擅自拆卸或移动。</li>'
            '<li>离场前请配合值班员清场检查。</li>'
            '</ul>'
        ).format(MEDITATION_NOTICE_MIN_READ_SECONDS, MEDITATION_MAX_USE_MINUTES,
                 MEDITATION_MIN_AHEAD_MINUTES, _checkin_room(), _meditation_room(),
                 MEDITATION_RESCHEDULE_LIMIT_MINUTES)

    return _ok({
        'title': '冥想室使用须知与承诺',
        'html': html,
        'min_read_seconds': MEDITATION_NOTICE_MIN_READ_SECONDS,
        'meditation_room': _meditation_room(),
        'checkin_room': _checkin_room(),
    })


def slots(request):
    """GET ?date=YYYY-MM-DD -> 该日各时段的占用情况。

    返回 taken=[[slot,seat],...] 供前端染色；同时给出每档已占数量，
    便于直接标"已满/可选"。一次查询取全，不按时段循环。
    """
    if request.method != 'GET':
        return _err('不支持的请求方式', http=405)

    res_date = parse_date(request.GET.get('date', ''))
    if res_date is None:
        return _err('日期参数不合法（应为 YYYY-MM-DD）')

    taken = models.Med_Reservation.taken_seats(res_date)
    per_slot = {}
    for slot_id, _label in MEDITATION_SLOTS:
        per_slot[slot_id] = 0
    for slot_id, _seat in taken:
        if slot_id in per_slot:
            per_slot[slot_id] += 1

    return _ok({
        'date': str(res_date),
        'taken': [[s, seat] for s, seat in taken],
        'seat_count': len(MEDITATION_SEAT_NUMBERS),
        'per_slot': [{'slot': sid, 'label': label,
                      'taken': per_slot[sid],
                      'full': per_slot[sid] >= len(MEDITATION_SEAT_NUMBERS)}
                     for sid, label in MEDITATION_SLOTS],
    })


@csrf_exempt
def submit(request):
    """POST 提交预约 -> 生成「未验证预约」（status=5），并推送提醒值班员。

    与 reservation_wps 同构：外部来源只落库为待验证，不直接进入处理流。
    """
    if request.method != 'POST':
        return _err('不支持的请求方式', http=405)

    payload = _payload(request)
    # 小程序带 token 时拿到 openid；对外网页端完全不带凭据，openid 为 None。
    # 两条路径都允许提交 —— 网页预约页本身就是免登录的。
    openid, auth_err = _resolve_identity(request, payload)
    if auth_err:
        return auth_err

    # 限流：按出口 IP 计。阈值取得较宽 —— 校园网 NAT 下同一 IP 代表很多人，
    # 定小了会误伤正常同学（见 _throttle 的注释）。可在 .env 调，设 0 关闭。
    if not _throttle(request, 'submit',
                     limit=getattr(settings, 'MEDITATION_SUBMIT_LIMIT_PER_IP', 60),
                     window_seconds=3600):
        return _err('提交过于频繁，请稍后再试')

    cleaned, error = _validate_submission(payload)
    if error:
        return _err('提交内容有误', error=error)

    phone = cleaned['mobile_phone']
    # 防重复：同一手机号存在未完成的预约时不允许再提交
    dup = models.Med_Reservation.objects.filter(
        mobile_phone=phone, res_form__status__in=(0, 1, 4, 5)).exists()
    if dup:
        return _err('你已有正在处理中的预约，请先完成或取消后再提交')

    try:
        with transaction.atomic():
            # 事务内复查座位，避免"读到空闲→写入"之间被抢占
            if models.Med_Reservation.is_seat_taken(
                    cleaned['res_date'], cleaned['slot'], cleaned['seat']):
                return _err('该座位刚被预约，请重新选择', error={'seat': '该座位已被预约'})

            uid = _next_uid()
            res = models.Med_Reservation.objects.create(
                uid=uid,
                name=cleaned['name'], sex=cleaned['sex'], college=cleaned['college'],
                grade=cleaned['grade'], stu_code=cleaned['stu_code'],
                mobile_phone=cleaned['mobile_phone'], email=cleaned['email'],
                res_date=cleaned['res_date'], slot=cleaned['slot'], seat=cleaned['seat'],
                note=cleaned['note'], agree=cleaned['agree'],
                # 有 openid = 微信小程序；没有 = 对外网页预约
                source=0 if openid else 3,
                wx_openid=openid, read_seconds=cleaned['read_seconds'],
            )
            models.Med_Form_Data.objects.create(res_form=res, status=5)
    except Exception as e:
        return _err('提交失败，请稍后重试（{}）'.format(e))

    # 推送提醒值班员（与平台既有做法一致；pusher id=3 为"预约单通知"模板）
    try:
        from django.urls import reverse
        url = "{scheme}://{host}{path}".format(
            scheme=request.scheme, host=request.get_host(),
            path=reverse('meditation_detail', kwargs={'uid': uid}),
        )
        send_pusher_by_id(3, {
            '内容': '小程序接收到新的冥想室预约，待验证',
            '单号': uid,
            '预约时间': format_res_datetime(cleaned['res_date'], cleaned['slot']),
            '座位': '{}号座'.format(cleaned['seat']),
            '验证链接': '<a href="{}">点击此处进行验证</a>'.format(url),
        })
    except Exception:
        # 推送失败不影响预约本身，不向用户暴露内部错误
        pass

    return _ok({
        'uid': uid,
        'res_date': str(cleaned['res_date']),
        'slot': cleaned['slot'],
        'slot_label': slot_label(cleaned['slot']),
        'seat': cleaned['seat'],
        'meditation_room': _meditation_room(),
        'checkin_room': _checkin_room(),
        'min_ahead_minutes': MEDITATION_MIN_AHEAD_MINUTES,
    }, msg='预约已提交，请牢记单号 {}'.format(uid))


@csrf_exempt
def my_list(request):
    """POST {"mobile_phone": ...} -> 该手机号下的预约列表。

    免登录：小程序与对外网页共用。凭手机号认领（与 _owns 同一套弱校验口径）。
    """
    if request.method != 'POST':
        return _err('不支持的请求方式', http=405)
    payload = _payload(request)
    _openid, auth_err = _resolve_identity(request, payload)
    if auth_err:
        return auth_err

    # 防枚举：查询是只读的，阈值可以更宽
    if not _throttle(request, 'mylist',
                     limit=getattr(settings, 'MEDITATION_LIST_LIMIT_PER_IP', 300),
                     window_seconds=3600):
        return _err('查询过于频繁，请稍后再试')

    phone = (payload.get('mobile_phone') or '').strip()
    if not phone:
        return _err('请填写手机号', error={'mobile_phone': '请填写手机号'})

    qs = models.Med_Reservation.objects.filter(mobile_phone=phone) \
        .select_related().order_by('-uid')[:30]
    items = []
    for r in qs:
        form = r.res_form.first()
        gate = _can_modify(r)
        items.append({
            'uid': r.uid,
            'name': r.name,
            'mobile_phone': r.mobile_phone,
            'res_date': str(r.res_date),
            'slot': r.slot,
            'slot_label': slot_label(r.slot),
            'seat': r.seat,
            'status': form.status if form else 0,
            'status_display': form.get_status_display() if form else '',
            'checkin_datetime': r.checkin_datetime.strftime('%Y-%m-%d %H:%M') if r.checkin_datetime else None,
            'checkout_datetime': r.checkout_datetime.strftime('%Y-%m-%d %H:%M') if r.checkout_datetime else None,
            'can_cancel': gate.get('ok', False),
            'cancel_reason': gate.get('reason', ''),
        })
    return _ok({'list': items})


def _can_modify(res_obj):
    """判断某预约当前是否允许用户自助改约/取消。

    规则：状态必须未终态；且距该时段开始时间 ≥ MEDITATION_RESCHEDULE_LIMIT_MINUTES。
    """
    form = res_obj.res_form.first()
    if form is None:
        return {'ok': False, 'reason': '预约单异常'}
    if form.status in (2, 3):
        return {'ok': False, 'reason': '该预约已结束或已取消'}
    start = _slot_start_dt(res_obj.res_date, res_obj.slot)
    if start is None:
        return {'ok': False, 'reason': '时段信息异常'}
    limit = start - datetime.timedelta(minutes=MEDITATION_RESCHEDULE_LIMIT_MINUTES)
    if datetime.datetime.now() > limit:
        return {'ok': False,
                'reason': '距开始不足 {} 分钟，请直接联系值班员'.format(
                    MEDITATION_RESCHEDULE_LIMIT_MINUTES)}
    return {'ok': True, 'reason': ''}


@csrf_exempt
def cancel(request):
    """POST {"uid": N} -> 用户自助取消。"""
    if request.method != 'POST':
        return _err('不支持的请求方式', http=405)
    payload = _payload(request)
    openid, auth_err = _resolve_identity(request, payload)
    if auth_err:
        return auth_err

    uid = payload.get('uid')
    res_obj = models.Med_Reservation.objects.filter(uid=uid).first() if uid else None
    if res_obj is None:
        return _err('预约单不存在')
    # 小程序按 openid 归属，网页按手机号归属（见 _owns）
    if not _owns(res_obj, openid, payload.get('mobile_phone')):
        return _err('只能操作本人的预约（请填写预约时使用的手机号）')

    gate = _can_modify(res_obj)
    if not gate['ok']:
        return _err(gate['reason'])

    with transaction.atomic():
        form = res_obj.res_form.first()
        form.status = 3  # 作废
        form.save(update_fields=['status'])
        _append_comment(form, '预约者自行取消')
    return _ok({'uid': res_obj.uid}, msg='已取消')


@csrf_exempt
def reschedule(request):
    """POST {"uid": N, "res_date": ..., "slot": ..., "seat": ...} -> 用户自助改约。"""
    if request.method != 'POST':
        return _err('不支持的请求方式', http=405)
    payload = _payload(request)
    openid, auth_err = _resolve_identity(request, payload)
    if auth_err:
        return auth_err

    uid = payload.get('uid')
    res_obj = models.Med_Reservation.objects.filter(uid=uid).first() if uid else None
    if res_obj is None:
        return _err('预约单不存在')
    if not _owns(res_obj, openid, payload.get('mobile_phone')):
        return _err('只能操作本人的预约（请填写预约时使用的手机号）')

    gate = _can_modify(res_obj)
    if not gate['ok']:
        return _err(gate['reason'])

    cleaned, error = _validate_submission({
        **payload,
        'name': res_obj.name, 'mobile_phone': res_obj.mobile_phone,
        'agree': 1, 'read_seconds': MEDITATION_NOTICE_MIN_READ_SECONDS,
    })
    if error:
        return _err('提交内容有误', error=error)

    with transaction.atomic():
        if models.Med_Reservation.is_seat_taken(
                cleaned['res_date'], cleaned['slot'], cleaned['seat'],
                exclude_uid=res_obj.uid):
            return _err('该座位刚被预约，请重新选择', error={'seat': '该座位已被预约'})
        res_obj.res_date = cleaned['res_date']
        res_obj.slot = cleaned['slot']
        res_obj.seat = cleaned['seat']
        res_obj.save(update_fields=['res_date', 'slot', 'seat'])
        _append_comment(res_obj.res_form.first(),
                        '预约者自行改约至 {} {}，{}号座'.format(
                            cleaned['res_date'], slot_label(cleaned['slot']), cleaned['seat']))

    return _ok({
        'uid': res_obj.uid,
        'res_date': str(res_obj.res_date),
        'slot': res_obj.slot,
        'slot_label': slot_label(res_obj.slot),
        'seat': res_obj.seat,
    }, msg='改约成功')
