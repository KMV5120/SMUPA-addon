# -*- coding: utf-8 -*-
"""
冥想室预约表单 —— 与 web/forms/reservationForm.py 保持同构，便于照搬。

差异点：
  1. 去掉咨询专有字段（问题多选、危机评估、期望咨询师）。
  2. 新增冥想室专属字段：使用日期、时段、座位号。
  3. 新增"日期"格式校验（原有 validate_datetime_format 只认 '%Y-%m-%d %H:%M'）。
"""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from web import models
from web.forms.bootstrap import BootStrapForm
from web.meditation_constants import MEDITATION_SLOTS, MEDITATION_SEAT_NUMBERS


class NewMeditationForm(BootStrapForm, forms.ModelForm):
    """平台内代录冥想室预约单（值班员代同学填写）。"""
    mobile_phone = forms.CharField(
        label='手机号',
        validators=[RegexValidator(r'^(1[3|4|5|6|7|8|9])\d{9}$', '手机号格式错误')],
    )
    staff = forms.CharField(label='其他值班员', required=False)

    class Meta:
        model = models.Med_Reservation
        # uid 由视图算出后传入，不交给表单
        exclude = ['uid']

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    # ------------------------------------------------------------------
    # 日期 / 时段 / 座位
    # ------------------------------------------------------------------
    def clean_res_date(self):
        """使用日期不得早于今天。"""
        import datetime
        res_date = self.cleaned_data['res_date']
        if res_date < datetime.date.today():
            raise ValidationError('使用日期不能早于今天！')
        return res_date

    def clean_slot(self):
        slot = self.cleaned_data['slot']
        if slot not in dict(MEDITATION_SLOTS):
            raise ValidationError('时段不合法！')
        return slot

    def clean_seat(self):
        seat = self.cleaned_data['seat']
        if seat not in MEDITATION_SEAT_NUMBERS:
            raise ValidationError('座位号不合法！')
        return seat

    def clean(self):
        """跨字段校验：该 (日期, 时段, 座位) 是否已被占用。

        放在 clean() 而非 clean_seat()，因为需要同时拿到日期与时段。
        提交侧还有一层事务内复查（视图里），这里只是尽早给出友好提示。
        """
        cleaned = super().clean()
        res_date = cleaned.get('res_date')
        slot = cleaned.get('slot')
        seat = cleaned.get('seat')
        if res_date and slot is not None and seat is not None:
            # 编辑已有单子时要排除自身
            exclude_uid = self.instance.uid if self.instance and self.instance.pk else None
            if models.Med_Reservation.is_seat_taken(res_date, slot, seat, exclude_uid=exclude_uid):
                raise ValidationError({'seat': '该座位在该时段已被预约，请重新选择！'})
        return cleaned

    # ------------------------------------------------------------------
    # 其他值班员（照搬心理预约的写法）
    # ------------------------------------------------------------------
    def clean_staff(self):
        staff = self.cleaned_data['staff']
        staffs = staff.strip().split()
        if not staffs:
            return ''
        existing_staffs, missing_staffs = models.UserInfo.check_users_exist_by_names(staffs)
        if missing_staffs:
            raise ValidationError('以下值班员不存在：{}'.format(', '.join(missing_staffs)))
        if self.request.STAFF.user.username in staffs:
            raise ValidationError('值班员与登录账户重复！')
        return ' '.join(existing_staffs)


class NewMeditationInviteForm(BootStrapForm, forms.ModelForm):
    """小程序/外部推送建单用：不含 uid（由视图生成）。"""
    mobile_phone = forms.CharField(
        label='手机号',
        validators=[RegexValidator(r'^(1[3|4|5|6|7|8|9])\d{9}$', '手机号格式错误')],
    )

    class Meta:
        model = models.Med_Reservation
        exclude = ['uid']


class MedInviteForm(BootStrapForm, forms.ModelForm):
    """分享码生成表单，对应 InviteModelForm。"""

    class Meta:
        model = models.Med_Share
        fields = ['period', 'count']

    def clean_count(self):
        count = self.cleaned_data["count"]
        if int(count) > 10:
            count = 10
        elif int(count) <= 0:
            count = 1
        return count


# 满意度调查问卷：机制沿用心理预约的 5 题量表，
# 题目文案按冥想室语境重写（委托人确认"重设计为冥想室体验向"）。
MEDITATION_SURVEY_QUESTIONS = (
    ('question1', '你对本次冥想室的整体体验满意吗？'),
    ('question2', '冥想室的环境（整洁、安静、氛围）是否符合预期？'),
    ('question3', '设备（音波枕、投影、水波纹灯等）使用是否顺畅？'),
    ('question4', '值班员的引导与协助是否到位？'),
)


class MeditationSurveyForm(forms.Form):
    question1 = forms.IntegerField()
    question2 = forms.IntegerField()
    question3 = forms.IntegerField()
    question4 = forms.IntegerField()
    question5 = forms.CharField(max_length=1024, required=False)

    def _check_scale(self, value, field):
        if value < 1 or value > 5:
            raise ValidationError("值不合法！")
        return value

    def clean_question1(self):
        return self._check_scale(self.cleaned_data["question1"], 1)

    def clean_question2(self):
        return self._check_scale(self.cleaned_data["question2"], 2)

    def clean_question3(self):
        return self._check_scale(self.cleaned_data["question3"], 3)

    def clean_question4(self):
        return self._check_scale(self.cleaned_data["question4"], 4)

    def clean_question5(self):
        return self.cleaned_data["question5"]
