# -*- coding: utf-8 -*-
from datetime import datetime


def validate_datetime_format(text):
    try:
        # 尝试将文本解析为datetime对象
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")

        # 执行日期时间规则验证
        if 1 <= dt.month <= 12 and 1 <= dt.day <= 31 and 0 <= dt.hour <= 23 and 0 <= dt.minute <= 59:
            return True
        else:
            return False
    except ValueError:
        return False


def validate_date_format(text):
    """校验 'YYYY-MM-DD' 格式的纯日期串。

    冥想室模块的资源由「日期 + 固定时段档 + 座位号」三元组确定，
    日期与时段是分开的两个字段，不复用需要时分秒的 validate_datetime_format。
    """
    if not isinstance(text, str):
        return False
    try:
        datetime.strptime(text.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def parse_date(text):
    """把 'YYYY-MM-DD' 解析成 date；不合法返回 None（不抛异常，便于视图容错）。"""
    if not validate_date_format(text):
        return None
    return datetime.strptime(text.strip(), "%Y-%m-%d").date()
