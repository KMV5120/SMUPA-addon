# -*- coding: utf-8 -*-
"""
冥想室模板标签 —— 把业务常量暴露给模板。

为什么用模板标签而不是 context_processor：
    只有冥想室相关模板需要这些常量，改 settings.TEMPLATES 会让 **所有** 页面
    都多跑一遍 context processor；模板标签是按需加载，更精准。

为什么不用视图传：
    座位图在 4 个模板里复用（填写页 / 详情页 / 选座页 / 打印页），
    逐一传参容易漏，常量从这里统一取更可靠。
"""

from django import template

from web import meditation_constants as MC

register = template.Library()


@register.simple_tag
def med_seats():
    """17 个座位及其百分比坐标。[{'no':1,'x':5,'y':17}, ...]"""
    return MC.MEDITATION_SEATS


@register.simple_tag
def med_slots():
    """11 个时段档。((id, '8:20-9:00'), ...)"""
    return MC.MEDITATION_SLOTS


@register.simple_tag
def med_seat_numbers():
    return MC.MEDITATION_SEAT_NUMBERS


@register.simple_tag
def med_door():
    """门的位置坐标。{'x':4,'y':91}"""
    return MC.MEDITATION_DOOR


@register.simple_tag
def med_room():
    """冥想室本身（同学实际使用的地方）。"""
    from django.conf import settings
    return getattr(settings, 'MEDITATION_ROOM', '') or MC.MEDITATION_ROOM_DEFAULT


@register.simple_tag
def med_checkin_room():
    """签到 / 签退值班室（纸质签到在这里）。

    与 med_room 是两个不同的地方，模板里别混用：
    讲"使用/入室"用 med_room，讲"签到/签退/到场"用 med_checkin_room。
    """
    from django.conf import settings
    return (getattr(settings, 'MEDITATION_CHECKIN_ROOM', '')
            or MC.MEDITATION_CHECKIN_ROOM_DEFAULT)


@register.simple_tag
def med_limits():
    """业务阈值，供文案提示使用。"""
    return {
        'max_use_minutes': MC.MEDITATION_MAX_USE_MINUTES,
        'min_ahead_minutes': MC.MEDITATION_MIN_AHEAD_MINUTES,
        'reschedule_limit_minutes': MC.MEDITATION_RESCHEDULE_LIMIT_MINUTES,
        'notice_min_read_seconds': MC.MEDITATION_NOTICE_MIN_READ_SECONDS,
    }


@register.filter
def seat_in(seat_no, seat_list):
    """判断座位号是否在给定列表中（用于选座图染色）。"""
    try:
        return int(seat_no) in [int(s) for s in seat_list]
    except (TypeError, ValueError):
        return False
