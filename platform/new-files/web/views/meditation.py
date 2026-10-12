# -*- coding: utf-8 -*-
"""
冥想室预约 —— 平台端视图

逐函数对照 web/views/reservation.py 实现，保持"照搬"：
    列表页三个、详情页按 POST 的 method 字段分派十个动作、
    周历、分享码、操作历史、打印、满意度调查。

与心理预约的两处有意偏离（均在自检报告里说明过）：
  1. **不接 Res_Room 房间审批** —— 冥想室是"单房间 17 座并行"，
     与 Res_Room 的"整间房排他借用"语义不同；占用由 (日期,时段,座位) 表达。
  2. **"其他值班员"处理抽成 _resolve_staff / _bulk_record_staff** ——
     原实现把这十来行在校验和写库处重复了九遍，这里收敛成两个函数，
     行为完全一致但可维护性更好。
"""

import datetime
import json

from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, QueryDict
from django.shortcuts import render, reverse

from utils.SMTP import send_email
from utils.encrypt import init_code
from utils.validate_tools import parse_date
from utils.wx_pusher import send_pusher_by_id
from web import models
from web.forms.meditationForm import (
    NewMeditationForm,
    MedInviteForm,
    MeditationSurveyForm,
)
from web.meditation_constants import (
    MEDITATION_SLOTS,
    MEDITATION_SEATS,
    MEDITATION_DOOR,
    MEDITATION_SEAT_NUMBERS,
    MEDITATION_RESCHEDULE_LIMIT_MINUTES,
    format_res_datetime,
    slot_label,
)

# 详情页同一 URL 靠这个字段分派动作（照搬心理预约的约定）
ACTION_FIELD = 'method'


# ===========================================================================
# 内部工具
# ===========================================================================
def _next_uid():
    """取下一个单号。

    原实现在 reserveation.py 里用 `.last().uid + 1`（按主键排序），
    这里按 uid 显式倒序，语义更明确，且不依赖插入顺序。
    """
    last = models.Med_Reservation.objects.order_by('-uid').first()
    return (last.uid + 1) if last else 1


def _resolve_staff(request, staff_str, error_key='staff'):
    """校验"其他值班员"输入。

    返回 (useranmes, error_dict)。error_dict 为 None 表示通过。
    逻辑与 reservation.py 完全一致，只是不再重复九遍。
    """
    staff_str = (staff_str or '').strip()
    if not staff_str:
        return [], None
    staffs = staff_str.split()
    existing, missing = models.UserInfo.check_users_active_by_names(staffs)
    if missing:
        return [], {error_key: '以下值班员不存在或已冻结：{}'.format(', '.join(missing))}
    if request.STAFF.user.username in staffs:
        return [], {error_key: '值班员与登录账户重复！'}
    return existing, None


def _bulk_record_staff(instance, usernames, operation):
    """为"其他值班员"批量补操作记录（一次 bulk_create，避免 N 次 insert）。"""
    if not usernames:
        return
    users = {u.username: u for u in models.UserInfo.objects.filter(
        username__in=usernames, is_locked=False)}
    models.Med_Operation.objects.bulk_create([
        models.Med_Operation(operator=users[name], ope_form=instance, operation=operation)
        for name in usernames if name in users
    ])


def _validate_resource(res_date_str, slot, seat):
    """校验 (日期, 时段, 座位) 三元组，返回 (res_date, slot, seat, error_dict)。"""
    res_date = parse_date(res_date_str)
    if res_date is None:
        return None, None, None, {'res_date': '使用日期格式不合法（应为 YYYY-MM-DD）！'}
    if res_date < datetime.date.today():
        return None, None, None, {'res_date': '使用日期不能早于今天！'}
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return None, None, None, {'slot': '请选择时段！'}
    if slot not in dict(MEDITATION_SLOTS):
        return None, None, None, {'slot': '时段不合法！'}
    try:
        seat = int(seat)
    except (TypeError, ValueError):
        return None, None, None, {'seat': '请选择座位！'}
    if seat not in MEDITATION_SEAT_NUMBERS:
        return None, None, None, {'seat': '座位号不合法！'}
    return res_date, slot, seat, None


def _detail_context(request, uid):
    """详情页 GET 的上下文，供 GET 与动作异常回退时复用。"""
    obj = models.Med_Reservation.objects.filter(uid=int(uid)).first()
    if obj is None:
        return None
    status_data, now_status = get_meditation_status(uid)
    ope = models.Med_Operation.objects.filter(ope_form__uid=int(uid)) \
        .select_related('operator').order_by('-id')
    invite_form = MedInviteForm()

    # 该日期+时段下的座位占用，供详情页的座位图染色。
    # taken_seats 一次查完，不在模板里逐座位发查询。
    taken = models.Med_Reservation.taken_seats(obj.res_date, obj.slot) if obj.res_date else []
    occupied_seats = sorted({seat for _, seat in taken})

    return {
        'obj': obj,
        'uid': uid,
        'status_data': status_data,
        'now_status': now_status,
        'ope': ope,
        'invite_form': invite_form,
        'occupied_seats': occupied_seats,
        'slots': MEDITATION_SLOTS,
        'date_options': [datetime.date.today() + datetime.timedelta(days=i) for i in range(30)],
    }


# ===========================================================================
# 预约填写 / 列表
# ===========================================================================
def new_meditation(request):
    """平台内代录冥想室预约单（值班员代同学填写）。"""
    if request.method == "GET":
        uid = _next_uid()
        return render(request, 'meditation/new_reservation.html', locals())

    form = NewMeditationForm(request, data=request.POST)
    if form.is_valid():
        with transaction.atomic():
            instance = form.save(commit=False)
            instance.uid = _next_uid()
            instance.source = 1  # 平台代录
            instance.save()

            models.Med_Form_Data.objects.create(
                res_form=instance,
                filler=request.STAFF.user,
                processor=None,
                comment=None,
                status=0,
            )
            models.Med_Operation.objects.create(
                operator=request.STAFF.user, ope_form=instance, operation=0,
            )
            # 其他值班员一并记工作记录
            staff_names, staff_err = _resolve_staff(request, form.cleaned_data.get('staff'))
            if staff_err:
                transaction.set_rollback(True)
                return JsonResponse({'status': False, 'error': staff_err})
            _bulk_record_staff(instance, staff_names, 0)
        return JsonResponse({'status': True, 'uid': instance.uid})
    return JsonResponse({'status': False, 'error': form.errors})


def _paged(qs, request, per_page=10):
    pages = request.GET.get('page')
    paginator = Paginator(qs, per_page)
    try:
        return paginator.page(pages)
    except EmptyPage:
        return paginator.page(paginator.num_pages)
    except PageNotAnInteger:
        return paginator.page(1)


def _search_filter(qs, query):
    return qs.filter(
        Q(name__contains=query) | Q(mobile_phone=query) | Q(email=query)
        | Q(stu_code=query) | Q(note__contains=query)
        | Q(res_form__guide__contains=query)
    )


def meditation_list(request):
    """所有冥想室预约单。"""
    qs = models.Med_Reservation.objects.all()
    if request.GET.get('search'):
        qs = _search_filter(qs, request.GET.get('search'))
    res_list = _paged(qs.order_by('uid'), request)
    return render(request, 'meditation/meditation_list.html', locals())


def meditation_appoint_list(request):
    """预约未完成（status=0，待受理）。"""
    qs = models.Med_Reservation.objects.filter(res_form__status=0)
    if request.GET.get('search'):
        qs = _search_filter(qs, request.GET.get('search'))
    res_list = _paged(qs.order_by('uid'), request)
    return render(request, 'meditation/meditation_appoint_list.html', locals())


def meditation_receive_list(request):
    """接待未完成（status=1，已受理待到访/签退）。"""
    qs = models.Med_Reservation.objects.filter(res_form__status=1)
    if request.GET.get('search'):
        qs = _search_filter(qs, request.GET.get('search'))
    res_list = _paged(qs.order_by('uid'), request)
    return render(request, 'meditation/meditation_receive_list.html', locals())


# ===========================================================================
# 状态 / 进度条
# ===========================================================================
def get_meditation_status(uid):
    """构造详情页进度条数据：'阶段:操作者:时间:内容' 用逗号连接。

    与 reservation.get_status 输出格式一致，供 detail 页的 StepContentFn 渲染。

    实现说明：原实现用「先 format 一部分、再把剩余占位符当字面量传进去」的
    两趟 format 拼串，占位符数量必须与实参个数精确吻合，改一个字就 IndexError。
    这里改成显式构造阶段列表，可读且不会踩该坑。
    时间用**全角冒号**，否则会破坏 StepContentFn 里的 split(':')。
    """
    res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).last()
    status_code = res_form.status if res_form else 0
    if status_code < 1:
        now_status = "等待受理"
    elif status_code == 1:
        now_status = "等待到访"
    elif status_code == 5:
        now_status = "等待验证"
    else:
        now_status = "完成"

    res_obj = models.Med_Reservation.objects.filter(uid=uid).first()
    create_time = res_obj.create_datetime.strftime('%Y-%m-%d %H：%M')

    def last_operator(operation):
        """取某类操作的操作者与时间（可能多人、多次）。"""
        qs = models.Med_Operation.objects.filter(ope_form__uid=uid, operation=operation) \
            .select_related('operator').order_by('id')
        if not qs:
            return '', ''
        names = ' '.join(o.operator.username for o in qs)
        return names, qs.last().operate_datetime.strftime('%Y-%m-%d %H：%M')

    accept_name, accept_time = last_operator(2)    # 完成受理
    checkin_name, checkin_time = last_operator(4)  # 完成签到接待
    finish_name, finish_time = last_operator(11)   # 完成签退

    stages = (
        ('等待受理', res_obj.name, create_time, '小程序或值班员提交预约单'),
        ('预约受理', '冥想室值班组', accept_time or '暂无', '确认时段与座位'),
        ('等待到访', accept_name or '暂无', accept_time or '暂无', '预约成功等待到访'),
        ('等待接待', '冥想室值班组', checkin_time or '暂无', '现场签到入室'),
        ('完成', finish_name or '暂无', finish_time or '暂无', '签退完成'),
    )
    status_data = ', '.join(':'.join(stage) for stage in stages)
    return status_data, now_status


# ===========================================================================
# 详情 / 处理
# ===========================================================================
def meditation_detail(request, uid):
    if request.method == 'GET':
        ctx = _detail_context(request, uid)
        if ctx is None:
            return render(request, 'error.html', {'code': 404, 'msg': '冥想室预约单不存在！'})
        obj = ctx['obj']
        # 未验证的网络预约（小程序推送），只有主席助理以上可查看
        if obj.res_form.first().status == 5 and request.STAFF.user.user_type < 5:
            return render(request, 'error.html', {
                'code': 403,
                'msg': '此预约单为未验证的小程序预约，请等待值班主席助理验证后再查看！',
            })
        return render(request, 'meditation/detail_meditation.html', ctx)

    data = request.POST
    method = data.get(ACTION_FIELD)

    # ---- 通过验证（未验证预约 5 -> 待受理 0）----
    if method == 'reg':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        if instance is None or res_form is None:
            return JsonResponse({'status': False, 'error': {'__all__': '预约单不存在！'}})

        staff_names, staff_err = _resolve_staff(request, data.get('staff1'), 'staff1')
        if staff_err:
            return JsonResponse({'status': False, 'error': staff_err})

        with transaction.atomic():
            _bulk_record_staff(instance, staff_names, 9)
            res_form.status = 0
            res_form.filler = request.STAFF.user
            res_form.save()
            models.Med_Operation.objects.create(
                operator=request.STAFF.user, ope_form=instance, operation=9)
        return JsonResponse({'status': True})

    # ---- 添加工作记录 ----
    elif method == 'work':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        operation = data.get('operation')
        if not operation:
            return JsonResponse({'status': False, 'error': {'operation': '请选择操作类型'}})
        staff_names, staff_err = _resolve_staff(request, data.get('staff'), 'staff4')
        if staff_err:
            return JsonResponse({'status': False, 'error': staff_err})
        if not staff_names and not (data.get('staff') or '').strip():
            return JsonResponse({'status': False, 'error': {'staff4': '请输入值班员姓名'}})
        with transaction.atomic():
            _bulk_record_staff(instance, staff_names, int(operation))
        return JsonResponse({'status': True, 'msg': '工作记录已添加！'})

    # ---- 添加备注 ----
    elif method == 'add_comment':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        text = '{}:{}'.format(request.STAFF.user.username, data.get('comment', ''))
        res_form.comment = (res_form.comment + ' || ' + text) if res_form.comment else text
        res_form.save()
        models.Med_Operation.objects.create(
            operator=request.STAFF.user, ope_form=instance, operation=6)
        return JsonResponse({'status': True})

    # ---- 受理：确认时段与座位 ----
    elif method == 'reservation':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        if instance is None or res_form is None:
            return JsonResponse({'status': False, 'error': {'__all__': '预约单不存在！'}})

        # 未提交则沿用小程序已选的日期/时段/座位
        res_date, slot, seat, res_err = _validate_resource(
            data.get('res_date') or instance.res_date,
            data.get('slot') if data.get('slot') not in (None, '') else instance.slot,
            data.get('seat') if data.get('seat') not in (None, '') else instance.seat,
        )
        if res_err:
            return JsonResponse({'status': False, 'error': res_err})

        staff_names, staff_err = _resolve_staff(request, data.get('staff'), 'staff')
        if staff_err:
            return JsonResponse({'status': False, 'error': staff_err})

        guide = (data.get('guide') or '').strip()
        with transaction.atomic():
            # 事务内复查座位，避免"读到空闲→写入"之间被别人抢占
            if models.Med_Reservation.is_seat_taken(res_date, slot, seat, exclude_uid=uid):
                return JsonResponse({
                    'status': False,
                    'error': {'seat': '该座位在该时段已被占用，请重新选择！'},
                })
            instance.res_date, instance.slot, instance.seat = res_date, slot, seat
            instance.save()
            _bulk_record_staff(instance, staff_names, 2)
            res_form.processor = request.STAFF.user
            if guide:
                res_form.guide = guide
            res_form.res_datetime = format_res_datetime(res_date, slot)
            res_form.status = 1
            res_form.save()
            models.Med_Operation.objects.create(
                operator=request.STAFF.user, ope_form=instance, operation=2)
        return JsonResponse({'status': True})

    # ---- 改约 ----
    elif method == 'change':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        if instance is None or res_form is None:
            return JsonResponse({'status': False, 'error': {'__all__': '预约单不存在！'}})

        res_date, slot, seat, res_err = _validate_resource(
            data.get('res_date'), data.get('slot'), data.get('seat'))
        if res_err:
            return JsonResponse({'status': False, 'error': res_err})

        staff_names, staff_err = _resolve_staff(request, data.get('staff'), 'staff2')
        if staff_err:
            return JsonResponse({'status': False, 'error': staff_err})

        guide = (data.get('guide') or '').strip()
        with transaction.atomic():
            if models.Med_Reservation.is_seat_taken(res_date, slot, seat, exclude_uid=uid):
                return JsonResponse({
                    'status': False,
                    'error': {'seat': '该座位在该时段已被占用，请重新选择！'},
                })
            instance.res_date, instance.slot, instance.seat = res_date, slot, seat
            instance.save()
            _bulk_record_staff(instance, staff_names, 3)
            res_form.processor = request.STAFF.user
            if guide:
                res_form.guide = guide
            res_form.res_datetime = format_res_datetime(res_date, slot)
            res_form.status = 1
            res_form.save()
            models.Med_Operation.objects.create(
                operator=request.STAFF.user, ope_form=instance, operation=3)
        return JsonResponse({'status': True})

    # ---- 废弃 ----
    elif method == 'delete':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        reason = data.get('comment', '')
        text = '{}:【废弃原因】{}'.format(request.STAFF.user.username, reason)
        res_form.comment = (res_form.comment + ' || ' + text) if res_form.comment else text
        res_form.status = 3
        res_form.save()
        models.Med_Operation.objects.create(
            operator=request.STAFF.user, ope_form=instance, operation=6)
        models.Med_Operation.objects.create(
            operator=request.STAFF.user, ope_form=instance, operation=5)
        return JsonResponse({'status': True, 'msg': '预约单已废弃！'})

    # ---- 清空（回到待受理，由值班员重新受理）----
    elif method == 'clear':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        res_form.status = 0
        res_form.guide = None
        res_form.processor = None
        res_form.res_datetime = None
        res_form.save()
        # 清掉签到/签退痕迹，避免下一轮误判
        instance.checkin_datetime = None
        instance.checkout_datetime = None
        instance.save()
        models.Med_Operation.objects.create(
            operator=request.STAFF.user, ope_form=instance, operation=8)
        return JsonResponse({'status': True, 'msg': '已清空预约详情，请值班员重新受理'})

    # ---- 续约（复制成一张新单）----
    elif method == 'renewal':
        if not models.Med_Reservation.objects.filter(uid=uid).exists():
            return JsonResponse({'status': False, 'error': {'__all__': '预约单不存在！'}})
        old = models.Med_Reservation.objects.filter(uid=uid).first()

        res_date, slot, seat, res_err = _validate_resource(
            data.get('res_date'), data.get('slot'), data.get('seat'))
        if res_err:
            return JsonResponse({'status': False, 'error': res_err})
        staff_names, staff_err = _resolve_staff(request, data.get('staff'), 'staff5')
        if staff_err:
            return JsonResponse({'status': False, 'error': staff_err})

        guide = (data.get('guide') or '').strip()
        with transaction.atomic():
            if models.Med_Reservation.is_seat_taken(res_date, slot, seat):
                transaction.set_rollback(True)
                return JsonResponse({
                    'status': False,
                    'error': {'seat': '该座位在该时段已被占用，请重新选择！'},
                })
            new_uid = _next_uid()
            new_instance = models.Med_Reservation.objects.create(
                uid=new_uid,
                name=old.name, sex=old.sex, college=old.college, grade=old.grade,
                stu_code=old.stu_code, mobile_phone=old.mobile_phone, email=old.email,
                res_date=res_date, slot=slot, seat=seat,
                note=old.note, agree=old.agree, source=old.source,
                wx_openid=old.wx_openid, read_seconds=old.read_seconds,
            )
            models.Med_Form_Data.objects.create(
                res_form=new_instance,
                filler=request.STAFF.user,
                processor=request.STAFF.user,
                comment='【第{}单续约】'.format(uid),
                status=1,
                guide=guide or None,
                res_datetime=format_res_datetime(res_date, slot),
            )
            _bulk_record_staff(new_instance, staff_names, 10)
            models.Med_Operation.objects.create(
                operator=request.STAFF.user, ope_form=new_instance, operation=10)
        return JsonResponse({'status': True, 'msg': '续约成功！', 'new_uid': new_uid})

    # ---- 签到入室 ----
    elif method == 'checkin':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        if instance is None or res_form is None:
            return JsonResponse({'status': False, 'error': {'__all__': '预约单不存在！'}})
        if res_form.status in (2, 3):
            return JsonResponse({'status': False,
                                 'error': {'__all__': '该预约单已终态，无法签到！'}})

        staff_names, staff_err = _resolve_staff(request, data.get('staff'), 'staff6')
        if staff_err:
            return JsonResponse({'status': False, 'error': staff_err})

        with transaction.atomic():
            instance.checkin_datetime = datetime.datetime.now()
            instance.save()
            _bulk_record_staff(instance, staff_names, 4)
            # 直接到场的情况（现场登记）允许从待受理直接进入待到访
            res_form.processor = request.STAFF.user
            res_form.status = 1
            res_form.save()
            models.Med_Operation.objects.create(
                operator=request.STAFF.user, ope_form=instance, operation=4)
        return JsonResponse({'status': True, 'msg': '签到完成，请引导同学入室'})

    # ---- 签退完成（对应心理预约的 finish）----
    elif method == 'finish':
        instance = models.Med_Reservation.objects.filter(uid=uid).first()
        res_form = models.Med_Form_Data.objects.filter(res_form__uid=uid).first()
        if instance is None or res_form is None:
            return JsonResponse({'status': False, 'error': {'__all__': '预约单不存在！'}})

        staff_names, staff_err = _resolve_staff(request, data.get('staff'), 'staff3')
        if staff_err:
            return JsonResponse({'status': False, 'error': staff_err})

        with transaction.atomic():
            instance.checkout_datetime = datetime.datetime.now()
            instance.save()
            _bulk_record_staff(instance, staff_names, 11)
            res_form.status = 2
            res_form.save()
            models.Med_Operation.objects.create(
                operator=request.STAFF.user, ope_form=instance, operation=11)

        who = request.STAFF.user.username
        if staff_names:
            who = '{}|{}'.format(who, '|'.join(staff_names))
        return JsonResponse({'status': True, 'msg': '签退已完成，接待者：{}'.format(who)})

    # 未知动作
    return JsonResponse({'status': False, 'error': {'__all__': '不支持的请求方式'}})


# ===========================================================================
# 周历 —— 与心理预约不同：行是"时段档"而不是"小时"
# ===========================================================================
def meditation_calendar(request):
    """本周冥想室预约周历。

    心理预约按小时定位（7:00-20:00 共 14 行），但冥想室 11 档里有同日同时段的
    重叠小时（15:05 与 15:55 都在 15 点），照搬会重叠，故**按时段档定位**：
    行 = 11 个时段，列 = 周一至周日。
    """
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.isoweekday() - 1)
    sunday = monday + datetime.timedelta(days=6)

    # 一次性取本周所有未完成/待到访的单，避免按天循环查询
    res_all = models.Med_Reservation.objects.filter(
        res_date__gte=monday, res_date__lte=sunday,
        res_form__status__in=(0, 1),
    ).select_related().order_by('res_date', 'slot')

    # 按 (星期, 时段) 建索引，避免在模板里做变量索引
    # （Django 模板不支持 dict[变量] 这种取值）
    bucket = {}
    for item in res_all:
        status = item.res_form.first().status if item.res_form.exists() else 0
        bucket.setdefault((item.res_date.isoweekday(), item.slot), []).append({
            'uid': item.uid,
            'name': item.name,
            'seat': item.seat,
            'slot': item.slot,
            'status': status,
        })

    week_days = [
        (1, '周一', monday), (2, '周二', monday + datetime.timedelta(days=1)),
        (3, '周三', monday + datetime.timedelta(days=2)),
        (4, '周四', monday + datetime.timedelta(days=3)),
        (5, '周五', monday + datetime.timedelta(days=4)),
        (6, '周六', monday + datetime.timedelta(days=5)), (7, '周日', sunday),
    ]

    # 视图侧把二维表铺平成"行列表"，模板只做 for 循环即可
    calendar_rows = []
    for sid, label in MEDITATION_SLOTS:
        cells = []
        for wd, wname, wdate in week_days:
            cells.append({
                'date': wdate,
                'is_today': wdate == today,
                'events': bucket.get((wd, sid), []),
            })
        calendar_rows.append({'slot': sid, 'label': label, 'cells': cells})

    return render(request, 'meditation/calendar.html', locals())


# ===========================================================================
# 选座页 / 座位占用接口
# ===========================================================================
def meditation_selection(request):
    """平台端选座页：选日期+时段，看该时段的座位占用与预约明细。"""
    today = datetime.date.today()
    # 未来 14 天可选
    date_options = [today + datetime.timedelta(days=i) for i in range(14)]
    slots = MEDITATION_SLOTS
    return render(request, 'meditation/meditation_selection.html', locals())


def meditation_seat_map_api(request):
    """某日期某时段的座位占用情况（平台端与小程序共用）。

    GET ?date=YYYY-MM-DD&slot=N
    返回 {"status": true, "data": {"date":..., "slot":..., "taken":[[slot,seat],...],
                                   "occupied_seats":[...], "bookings":[...]}}
    """
    if request.method != 'GET':
        return JsonResponse({'status': False, 'msg': '不支持的访问方式'}, status=405)

    res_date = parse_date(request.GET.get('date', ''))
    if res_date is None:
        return JsonResponse({'status': False, 'msg': '日期参数不合法（应为 YYYY-MM-DD）'})

    slot_raw = request.GET.get('slot')
    slot = None
    if slot_raw not in (None, ''):
        try:
            slot = int(slot_raw)
        except (TypeError, ValueError):
            return JsonResponse({'status': False, 'msg': '时段参数不合法'})
        if slot not in dict(MEDITATION_SLOTS):
            return JsonResponse({'status': False, 'msg': '时段参数不合法'})

    # 一次取回该日期（可选时段）的全部占用，避免逐座位查询
    qs = models.Med_Reservation.objects.filter(
        res_date=res_date, res_form__status__in=models.MEDITATION_ACTIVE_STATUS,
    ).select_related()
    if slot is not None:
        qs = qs.filter(slot=slot)

    taken = []
    bookings = []
    for r in qs:
        taken.append([r.slot, r.seat])
        bookings.append({
            'uid': r.uid,
            'name': r.name,
            'slot': r.slot,
            'slot_label': slot_label(r.slot),
            'seat': r.seat,
            'status': r.res_form.first().status if r.res_form.exists() else 0,
        })

    return JsonResponse({
        'status': True,
        'data': {
            'date': str(res_date),
            'slot': slot,
            'taken': taken,
            'occupied_seats': sorted({s for _, s in taken}) if slot is not None else [],
            'bookings': bookings,
        },
    })


# ===========================================================================
# 分享码 / 操作历史 / 打印 / 调查（照搬心理预约）
# ===========================================================================
def med_share_code(request, res_id):
    form = MedInviteForm(data=request.POST)
    if form.is_valid():
        res_obj = models.Med_Reservation.objects.filter(id=res_id).first()
        if res_obj is None:
            return JsonResponse({'status': False, 'error': {'__all__': '预约单不存在！'}})
        form.instance.consult = res_obj
        form.instance.code = init_code(request.STAFF.user.mobile_phone)
        form.instance.creator = request.STAFF.user
        form.save()
        url = "{scheme}://{host}{path}".format(
            scheme=request.scheme, host=request.get_host(),
            path=reverse('med_share_visit', kwargs={'code': form.instance.code}),
        )
        return JsonResponse({'status': True, 'data': url})
    return JsonResponse({'status': False, 'error': form.errors})


def med_share_visit(request, code):
    current_datetime = datetime.datetime.now()
    invite_object = models.Med_Share.objects.filter(code=code).first()
    if not invite_object:
        return render(request, 'error.html', {'code': 404, 'msg': '分享码不存在'})

    limit_datetime = invite_object.create_datetime + datetime.timedelta(minutes=invite_object.period)
    if current_datetime > limit_datetime:
        return render(request, 'error.html', {'code': 404, 'msg': '预约详情分享已过期'})

    if invite_object.count:
        if invite_object.use_count >= invite_object.count:
            return render(request, 'error.html',
                          {'code': 404, 'msg': '访问次数已用尽！请联系心协值班员重新发送链接！'})
        invite_object.use_count += 1
        invite_object.save()

    obj = invite_object.consult
    use_count = invite_object.use_count
    rest_count = invite_object.count - use_count
    staff = invite_object.creator
    ip = request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT')
    return render(request, 'meditation/share_meditation.html', locals())


def med_operate_history(request):
    return render(request, 'meditation/operate_history.html', locals())


def med_api_history(request):
    """操作历史 JSON。只查 Med_Operation 表，绝不混入心理预约的 Operation。"""
    if request.method != 'GET':
        return JsonResponse({'status': False, 'error': 'invalid request method!'})
    count = request.GET.get('count')
    try:
        if count:
            count = int(count)
            count = 500 if count >= 500 else (1 if count <= 1 else count)
            ope_list = models.Med_Operation.objects.select_related('operator', 'ope_form') \
                .order_by('-id')[:count]
        else:
            today = datetime.datetime.now()
            ope_list = models.Med_Operation.objects.select_related('operator', 'ope_form').filter(
                Q(operate_datetime__year=today.year)
                & Q(operate_datetime__month=today.month)
                & Q(operate_datetime__day=today.day)
            ).order_by('-id')
    except BaseException:
        return JsonResponse({'status': False, 'error': '服务器错误，请联系管理员！'})

    return JsonResponse({
        'status': True,
        'data': [{
            'uid': i.ope_form.uid,
            'time': i.operate_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            'operator': i.operator.username,
            'operation': i.operation,
        } for i in ope_list],
    })


def med_api_check_statistics(request):
    """今日各项操作统计（督导查班用）。"""
    if request.method != 'GET':
        return JsonResponse({'status': False, 'error': 'invalid request method!'})
    today = datetime.datetime.today()

    def cnt(operation):
        return models.Med_Operation.objects.filter(
            Q(operation=operation)
            & Q(operate_datetime__year=today.year)
            & Q(operate_datetime__month=today.month)
            & Q(operate_datetime__day=today.day)
        ).count()

    return JsonResponse({'status': True, 'data': [
        {'name': "appointment-today", 'num': cnt(2)},
        {'name': "reception-today", 'num': cnt(4)},
        {'name': "re-appointment-today", 'num': cnt(3)},
        {'name': "cancel-today", 'num': cnt(5)},
    ]})


def print_meditation(request, uid):
    if request.method != 'GET':
        return JsonResponse({'status': False, 'msg': '不合法的请求方式！'})
    res_obj = models.Med_Reservation.objects.filter(uid=int(uid)).first()
    if not res_obj:
        return JsonResponse({'status': False, 'msg': '预约单不存在！'})
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render(request, 'meditation/res_print.html', locals())


def meditation_survey(request, res_id, code):
    """满意度调查（公开，凭 code 访问）。"""
    exists = models.Med_Form_Data.objects.filter(res_form_id=res_id).exists()
    if not exists:
        return render(request, 'error.html', {'code': 404, 'msg': '预约单不存在！'})
    res_obj = models.Med_Form_Data.objects.filter(res_form_id=res_id).first()
    if res_obj.is_survey_completed:
        return render(request, 'error.html', {'code': 401, 'msg': '该反馈已完成，感谢您的支持！'})
    if code != res_obj.survey_code:
        return render(request, 'error.html', {'code': 401, 'msg': '校验失败，无权限访问！'})

    if request.method == 'GET':
        return render(request, 'meditation/survey.html', locals())

    data = dict(request.POST)
    data.pop('csrfmiddlewaretoken', None)
    form = MeditationSurveyForm(request.POST)
    if form.is_valid():
        res_obj.is_survey_completed = True
        res_obj.survey_data = json.dumps(data)
        res_obj.save()
        return JsonResponse({'status': True, 'msg': '提交成功！'})
    return JsonResponse({'status': False, 'msg': '提交失败，请检查！', 'error': form.errors})


def send_meditation_survey(request, res_id):
    """发送满意度调查邀请邮件。

    注意：**邮件正文与链接由委托人另行提供**，此处为占位实现 ——
    机制（校验码生成、状态回写、防重复发送）与心理预约完全一致，
    只有正文文案是临时占位，拿到正式文案后替换 content 即可。
    """
    if request.method != "GET":
        return JsonResponse({'status': False, 'msg': '不合法的请求方式！'})
    if request.STAFF.user.user_type < 4:
        return JsonResponse({'status': False, 'msg': '权限不足！'})
    res_obj = models.Med_Form_Data.objects.filter(res_form_id=res_id).first()
    if res_obj is None:
        return JsonResponse({'status': False, 'msg': '预约单不存在！'})
    if res_obj.status != 2:
        return JsonResponse({'status': False, 'msg': '预约状态错误！'})
    if res_obj.invited:
        return JsonResponse({'status': False, 'msg': '请勿重复发送调查邀请！'})

    random_code = init_code("{}{}".format(res_obj.res_form_id, res_obj.res_datetime))
    url = "{scheme}://{host}{path}".format(
        scheme=request.scheme, host=request.get_host(),
        path=reverse('meditation_survey', kwargs={'res_id': res_obj.res_form_id, 'code': random_code}),
    )
    # ---- 占位正文（待委托人提供正式文案与链接）----
    content = (
        '<p>同学你好：</p>'
        '<p>感谢你使用冥想室。为了更好地改进服务，邀请你对本次体验做个简短评价。</p>'
        '<p>预约时间：{}</p>'
        '<p><a href="{}">点此参与评价</a></p>'
    ).format(res_obj.res_datetime, url)

    email = res_obj.res_form.email
    if not email:
        return JsonResponse({'status': False, 'msg': '该预约单没有邮箱，无法发送邀请！'})

    res = send_email(email, 'SMUPA冥想室体验反馈邀请', content, 'html')
    if res.get("code") == 0:
        res_obj.survey_code = random_code
        res_obj.invited = True
        res_obj.save()
        return JsonResponse({'status': True, 'msg': '发送成功！'})
    return JsonResponse({'status': False, 'msg': '发送失败！'})


def med_survey_api_output(request, key):
    """调查数据对外接口（与心理预约同构，独立 key 可复用同一配置）。"""
    if request.method != "GET":
        return JsonResponse({'code': 502, 'message': 'Error: refused!', 'data': []})
    if not settings.SURVEY_API_KEY or key != settings.SURVEY_API_KEY:
        return JsonResponse({'code': 401, 'message': 'Error: wrong key!', 'data': []})
    res_data = {'code': 200, 'message': 'success', 'data': []}
    for item in models.Med_Form_Data.objects.filter(is_survey_completed=True):
        res_data['data'].append({
            'res_id': item.res_form.uid,
            'guide': item.guide,
            'res_datetime': item.res_datetime,
            **json.loads(item.survey_data or '{}'),
        })
    return JsonResponse(res_data)
