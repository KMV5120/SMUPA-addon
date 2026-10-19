# -*- coding: utf-8 -*-
"""管理员上线前的迁移演练（临时 SQLite，不碰生产库）。

由 golive.py 在 golive_rehearsal_settings 下调用。
"""
import datetime
import io
import os
import sys

import django

django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402

from web import models  # noqa: E402

# 硬门禁：只允许写 golive.py 创建的临时 SQLite，绝不碰生产库
_expected = os.environ.get('SMUPA_GOLIVE_TEMP_DB')
_actual = os.path.abspath(settings.DATABASES['default']['NAME'])
if (not _expected
        or _actual != os.path.abspath(_expected)
        or 'rehearsal.sqlite3' not in _actual):
    print('REFUSING: not a golive rehearsal DB')
    print('  expected = {!r}'.format(_expected))
    print('  actual   = {!r}'.format(_actual))
    sys.exit(3)
from web.meditation_constants import format_res_datetime  # noqa: E402

FAIL = []


def check(name, got, want):
    if got == want:
        print('  OK   {}'.format(name))
    else:
        FAIL.append(name)
        print('  FAIL {}  期望={!r} 实际={!r}'.format(name, want, got))


def next_open(days=7):
    d = datetime.date.today() + datetime.timedelta(days=days)
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


def make(uid, slot, seat, status, comment=None, with_form=True, created=None):
    res = models.Med_Reservation.objects.create(
        uid=uid, name='演练{}'.format(uid), sex=0, college=0, grade=2,
        mobile_phone='139{:08d}'.format(uid % 100000000),
        res_date=next_open(), slot=slot, seat=seat, note='golive',
        agree=1, source=3,
    )
    form = None
    if with_form:
        form = models.Med_Form_Data.objects.create(
            res_form=res, status=status, comment=comment,
            res_datetime=(format_res_datetime(res.res_date, slot)
                          if status in (1, 2) else None),
        )
    models.Med_Reservation.objects.filter(uid=uid).update(
        create_datetime=created or (datetime.datetime.now()
                                    - datetime.timedelta(days=2)))
    return res, form


def main():
    now = datetime.datetime.now()
    cutoff = (now - datetime.timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M')

    r1, f1 = make(80001, 1, 1, 1)
    r4, f4 = make(80002, 4, 2, 5)
    r5, f5 = make(80003, 5, 3, 0)
    r0, f0 = make(80004, 0, 4, 1)
    r2, f2 = make(80005, 2, 5, 2)
    long_res, long_form = make(80006, 1, 6, 1, comment='x' * 250)
    conflict_old, conflict_form = make(80007, 1, 7, 1)
    conflict_new, _ = make(80008, 0, 7, 1, created=now)
    missing, _ = make(80009, 4, 8, 1, with_form=False)
    new_res, _ = make(80010, 0, 9, 1, created=now)

    before = list(models.Med_Reservation.objects.order_by('uid').values_list(
        'uid', 'slot'))
    call_command('repair_meditation_slots', '--dry-run',
                 '--cutoff', cutoff, stdout=io.StringIO())
    after_dry = list(models.Med_Reservation.objects.order_by('uid').values_list(
        'uid', 'slot'))
    check('dry-run 不写库', after_dry, before)

    call_command('repair_meditation_slots', '--apply',
                 '--cutoff', cutoff, stdout=io.StringIO())

    r1.refresh_from_db(); r4.refresh_from_db(); r5.refresh_from_db()
    r0.refresh_from_db(); f0.refresh_from_db()
    check('旧 1 -> 新 0', r1.slot, 0)
    check('旧 4 -> 新 3', r4.slot, 3)
    check('旧 5 -> 新 4', r5.slot, 4)
    check('旧 0 作废', f0.status, 3)
    check('旧 2 历史保留', models.Med_Form_Data.objects.get(
        res_form=r2).status, 2)
    check('迁移记录 remap',
          models.Med_SlotMigration.objects.get(reservation=r1).action,
          'remap')
    check('长备注保留标记',
          '【时段迁移】' in (models.Med_Form_Data.objects.get(
              res_form=long_res).comment or ''), True)
    conflict_old.refresh_from_db()
    check('冲突不自动改号', conflict_old.slot, 1)
    check('冲突有记录',
          models.Med_SlotMigration.objects.get(
              reservation=conflict_old).action, 'conflict')
    check('缺 form 跳过',
          models.Med_SlotMigration.objects.filter(
              reservation=missing).exists(), False)
    new_res.refresh_from_db()
    check('cutoff 后新单不动', new_res.slot, 0)

    snap = list(models.Med_Reservation.objects.order_by('uid').values_list(
        'uid', 'slot'))
    call_command('repair_meditation_slots', '--apply',
                 '--cutoff', cutoff, stdout=io.StringIO())
    check('重复 apply 无变化',
          list(models.Med_Reservation.objects.order_by('uid').values_list(
              'uid', 'slot')), snap)

    print('\n演练失败 {} 项'.format(len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
