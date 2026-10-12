# -*- coding: utf-8 -*-
"""
冥想室业务常量 —— 平台端与微信小程序共用的唯一数据源。

为什么单独成文件而不放 settings：
    时段表、座位坐标是**固定业务规则**，不是"部署环境差异"，不属于 settings 的职责；
    同时它们被 models / forms / views / templates 以及小程序接口五处引用，
    放这里可以被 web 包内任意位置 import，并原样通过接口吐给小程序，
    保证"平台端选座图"与"小程序选座图"用的是同一份坐标，不会画歪。

坐标说明：
    全部为**百分比**（相对容器宽/高），按 seat.jpg 归一化。
    渲染时用  position:absolute; left:x%; top:y%; transform:translate(-50%,-50%)
    让图形中心落在坐标点上，这样容器按任意尺寸缩放都不会错位。
"""

# ---------------------------------------------------------------------------
# 时段：固定 11 档，每档 40 分钟
# ---------------------------------------------------------------------------
MEDITATION_SLOTS = (
    (0, '8:20-9:00'),
    (1, '9:10-9:50'),
    (2, '10:15-10:55'),
    (3, '11:05-11:45'),
    (4, '13:10-13:50'),
    (5, '14:00-14:40'),
    (6, '15:05-15:45'),
    (7, '15:55-16:35'),
    (8, '18:00-18:40'),
    (9, '18:50-19:30'),
    (10, '19:40-20:20'),
)

# 拆出起止时间，供"提前 N 分钟才能改约/取消"一类的校验使用
MEDITATION_SLOT_START = {
    0: '08:20', 1: '09:10', 2: '10:15', 3: '11:05', 4: '13:10', 5: '14:00',
    6: '15:05', 7: '15:55', 8: '18:00', 9: '18:50', 10: '19:40',
}
MEDITATION_SLOT_END = {
    0: '09:00', 1: '09:50', 2: '10:55', 3: '11:45', 4: '13:50', 5: '14:40',
    6: '15:45', 7: '16:35', 8: '18:40', 9: '19:30', 10: '20:20',
}

MEDITATION_SLOT_IDS = tuple(sid for sid, _ in MEDITATION_SLOTS)


# ---------------------------------------------------------------------------
# 座位：共 17 个，坐标按 seat.jpg 归一化
#   布局：左列 1-4（自上而下）、右列 5-9（自上而下）、
#         中间左列 10-13、中间右列 14-17，左下角为门
# ---------------------------------------------------------------------------
MEDITATION_SEAT_COUNT = 17

MEDITATION_SEATS = (
    # 左列（4 座）
    {'no': 1,  'x': 5,  'y': 17},
    {'no': 2,  'x': 5,  'y': 35},
    {'no': 3,  'x': 5,  'y': 53},
    {'no': 4,  'x': 5,  'y': 70},
    # 右列（5 座，比左列多一个）
    {'no': 5,  'x': 95, 'y': 17},
    {'no': 6,  'x': 95, 'y': 33},
    {'no': 7,  'x': 96, 'y': 52},
    {'no': 8,  'x': 96, 'y': 70},
    {'no': 9,  'x': 96, 'y': 88},
    # 中间左列（4 座）
    {'no': 10, 'x': 33, 'y': 27},
    {'no': 11, 'x': 33, 'y': 43},
    {'no': 12, 'x': 33, 'y': 59},
    {'no': 13, 'x': 33, 'y': 75},
    # 中间右列（4 座）
    {'no': 14, 'x': 64, 'y': 27},
    {'no': 15, 'x': 64, 'y': 43},
    {'no': 16, 'x': 64, 'y': 59},
    {'no': 17, 'x': 64, 'y': 75},
)

MEDITATION_DOOR = {'x': 4, 'y': 91}

MEDITATION_SEAT_NUMBERS = tuple(s['no'] for s in MEDITATION_SEATS)

# Django choices 需要静态元组，不能是生成器
MEDITATION_SEAT_CHOICES = tuple((n, '{}号座'.format(n)) for n in MEDITATION_SEAT_NUMBERS)


# ---------------------------------------------------------------------------
# 业务阈值（来自《冥想室使用流程与相关注意事项》）
# ---------------------------------------------------------------------------
MEDITATION_MAX_USE_MINUTES = 40          # 单次使用时长上限（由固定时段天然满足）
MEDITATION_MIN_AHEAD_MINUTES = 5         # 须至少提前 N 分钟到值班室现场签到
MEDITATION_RESCHEDULE_LIMIT_MINUTES = 60  # 改约/取消须至少提前 N 分钟
MEDITATION_NOTICE_MIN_READ_SECONDS = 5   # 《须知与承诺》最短阅读时长

# 房间文案。注意这是**两个不同的地方**（《使用流程》原文：
# "须至少提前五分钟前往 412 值班室进行现场签到，由值班员引导进入冥想室"）：
#   MEDITATION_ROOM          —— 冥想室本身，同学实际使用的地方
#   MEDITATION_CHECKIN_ROOM  —— 签到值班室，纸质签到/签退在这里
# 两者的文案都可能变，故分开配置，勿合并。
# 可由 settings.MEDITATION_ROOM / MEDITATION_CHECKIN_ROOM 覆盖。
MEDITATION_ROOM_DEFAULT = '410B'
MEDITATION_CHECKIN_ROOM_DEFAULT = '412'


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
_SLOT_LABEL_MAP = dict(MEDITATION_SLOTS)


def slot_label(slot_id):
    """取某个时段的展示文本，非法值返回空串（不抛异常，便于模板/接口容错）。"""
    try:
        return _SLOT_LABEL_MAP.get(int(slot_id), '')
    except (TypeError, ValueError):
        return ''


def slot_time_range(slot_id):
    """取某个时段的 (开始, 结束) 字符串，如 ('08:20', '09:00')。"""
    try:
        sid = int(slot_id)
    except (TypeError, ValueError):
        return None
    if sid in MEDITATION_SLOT_START:
        return MEDITATION_SLOT_START[sid], MEDITATION_SLOT_END[sid]
    return None


def seat_label(seat_no):
    """取座位展示文本，非法值返回空串。"""
    try:
        n = int(seat_no)
    except (TypeError, ValueError):
        return ''
    return '{}号座'.format(n) if n in MEDITATION_SEAT_NUMBERS else ''


def format_res_datetime(res_date, slot_id):
    """把 (日期, 时段) 拼成反规范化的展示串，如 '2026-10-15 8:20-9:00'。

    心理预约模块用 Med_Form_Data.res_datetime 这一个字符串承载"预约时间"，
    冥想室沿用同一字段以便周历/打印/调查页几乎原样复用，这里负责生成它。
    """
    if not res_date:
        return ''
    label = slot_label(slot_id)
    if not label:
        return str(res_date)
    return '{} {}'.format(res_date, label)


def as_json():
    """供小程序接口吐出的 JSON 结构（时段 + 座位 + 门 + 阈值）。

    平台端与小程序端都消费这一份数据，从根本上避免两端布局不一致。
    """
    return {
        'slots': [
            {
                'id': sid,
                'label': label,
                'start': MEDITATION_SLOT_START[sid],
                'end': MEDITATION_SLOT_END[sid],
            }
            for sid, label in MEDITATION_SLOTS
        ],
        'seats': [dict(s) for s in MEDITATION_SEATS],
        'door': dict(MEDITATION_DOOR),
        'seat_count': MEDITATION_SEAT_COUNT,
        # 两个房间都下发，前端按语境取用（勿混用）
        'meditation_room': MEDITATION_ROOM_DEFAULT,
        'checkin_room': MEDITATION_CHECKIN_ROOM_DEFAULT,
        'max_use_minutes': MEDITATION_MAX_USE_MINUTES,
        'min_ahead_minutes': MEDITATION_MIN_AHEAD_MINUTES,
        'reschedule_limit_minutes': MEDITATION_RESCHEDULE_LIMIT_MINUTES,
        'notice_min_read_seconds': MEDITATION_NOTICE_MIN_READ_SECONDS,
    }
