import json
from typing import List, Tuple

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import models

from multiselectfield import MultiSelectField

from web.meditation_constants import (
    MEDITATION_SLOTS,
    MEDITATION_SEAT_CHOICES,
)

# 选项，注意，若修改选项，前端也应作相应修改
college_choice = (
    (0, '商船学院'),
    (1, '交通运输学院'),
    (2, '经济管理学院'),
    (3, '物流工程学院'),
    (4, '信息工程学院'),
    (5, '外国语学院'),
    (6, '理学院'),
    (7, '法学院'),
    (8, '海洋科学与工程学院'),
    (9, '物流科学与工程研究院'),
    (11, '马克思主义学院'),
    (12, '徐悲鸿艺术学院'),
    (10, '其他'),
)


# Create your models here.
class UserInfo(models.Model):
    '''成员表'''
    user_type_choice = (
        (0, '往届成员'),
        (1, '干事'),
        (2, '副部长'),
        (3, '部长'),
        (4, '督导组'),
        (5, '主席助理'),
        (6, '主席'),
        (7, '负责老师'),
    )
    apartment_choice = (
        (0, '调研部'),
        (1, '网宣部'),
        (2, '外联部'),
        (3, '组织部'),
        (5, '学术部'),
        (6, '行政部'),
        (7, '主席团'),
        (8, '办公室'),
    )

    username = models.CharField(verbose_name='成员姓名', max_length=32)  # db_index=True 索引
    stu_code = models.CharField(verbose_name='学号/工号', max_length=12, db_index=True, unique=True)
    email = models.EmailField(verbose_name='邮箱', max_length=32)
    mobile_phone = models.CharField(verbose_name='手机号', max_length=32)
    password = models.CharField(verbose_name='密码', max_length=32)
    user_type = models.SmallIntegerField(verbose_name='职务', choices=user_type_choice, default=1)
    apartment = models.SmallIntegerField(verbose_name='部门', choices=apartment_choice)
    college = models.SmallIntegerField(verbose_name='学院', choices=college_choice, default=10)
    class_name = models.CharField(verbose_name='班级', max_length=32)
    is_locked = models.BooleanField(verbose_name="是否冻结", default=True)
    wx_uid = models.CharField(verbose_name='微信uid', max_length=128, null=True, blank=True)

    # session_key = models.CharField(verbose_name='session_key', max_length=256, null=True, blank=True)
    class Meta:
        verbose_name_plural = "心协成员表"

    def __str__(self):
        return self.username

    @classmethod
    def check_users_exist_by_names(cls, name_list: List[str]) -> Tuple[List[str], List[str]]:
        existing_users: List[str] = list(cls.objects.filter(username__in=name_list).values_list('username', flat=True))
        missing_users: List[str] = [name for name in name_list if name not in existing_users]
        return existing_users, missing_users

    @classmethod
    def check_users_active_by_names(cls, name_list: List[str]) -> Tuple[List[str], List[str]]:
        existing_users: List[str] = list(
            cls.objects.filter(username__in=name_list, is_locked=False).values_list('username', flat=True))
        missing_users: List[str] = [name for name in name_list if name not in existing_users]
        return existing_users, missing_users


class UserCheck(models.Model):
    user = models.ForeignKey(to='UserInfo', verbose_name="成员", on_delete=models.CASCADE)
    is_read = models.BooleanField(verbose_name="是否审阅", default=False)


class Notification(models.Model):
    priority_choices = (
        (0, '次要'),
        (1, '普通'),
        (2, '较重要'),
        (3, '重要'),
        (4, '非常重要'),
    )
    title = models.CharField(verbose_name='标题', max_length=128)
    publisher = models.ForeignKey(to='UserInfo', verbose_name="发布者", on_delete=models.CASCADE)
    content = models.TextField(verbose_name='内容', max_length=20480)
    priority = models.SmallIntegerField(verbose_name='重要级', choices=priority_choices, default=1)
    date = models.DateField(verbose_name='发布日期', auto_now_add=True)

    class Meta:
        verbose_name_plural = "通知表"
        ordering = ['-date', '-priority']

    def __str__(self):
        return self.title


class LoginTime(models.Model):
    user = models.ForeignKey(to="UserInfo", related_name="user", on_delete=models.CASCADE)
    login_time = models.DateTimeField(verbose_name='登陆时间', auto_now_add=True)
    ip = models.CharField(verbose_name="ip地址", max_length=32)
    agent = models.CharField(verbose_name="", max_length=64)

    class Meta:
        verbose_name_plural = "登陆监控"
        ordering = ['-id']

    def __str__(self):
        return "{} ｜ {} ｜ {}".format(self.user.username, self.login_time.strftime('%Y/%m/%d %H:%M:%S'), self.ip)


class Reservation(models.Model):
    sex_choice = (
        (0, '女'),
        (1, '男'),
        (2, '其他或不便透露'),

    )

    grade_choice = (
        (0, '预科'),
        (1, '大一'),
        (2, '大二'),
        (3, '大三'),
        (4, '大四'),
        (5, '硕一'),
        (6, '硕二'),
        (7, '博一'),
        (8, '博二'),
        (9, '其他'),

    )

    renji_choice = (
        (0, '暂无'),
        (1, '人际关系不良'),
        (2, '家庭关系'),
        (3, '宿舍关系'),
        (4, '其他'),
    )

    qinggan_choice = (
        (0, '暂无'),
        (1, '失恋'),
        (2, '恋爱困惑'),
        (3, '其他'),
    )

    xueye_choice = (
        (0, '暂无'),
        (1, '学习压力'),
        (2, '厌学'),
        (3, '专业不感兴趣'),
        (4, '作弊处分'),
        (5, '挂科'),
        (6, '延期毕业'),
        (7, '网络成瘾'),
        (8, '考研压力'),
        (9, '其他'),
    )

    zhiye_choice = (
        (0, '暂无'),
        (1, '职业规划'),
        (2, '职业选择'),
        (3, '其他'),
    )

    qingxu_choice = (
        (0, '暂无'),
        (1, '抑郁'),
        (2, '焦虑'),
        (3, '强迫'),
        (4, '恐惧'),
        (5, '疑病'),
        (6, '饮食障碍'),
    )

    xingxin_choice = (
        (0, '暂无'),
        (1, '性困惑'),
        (2, '同性恋'),
        (3, '其他'),
    )

    age_choice = (
        (0, '20-40'),
        (1, '40-50'),
        (2, '50以上'),
        (3, '不介意')
    )

    where_choice = (
        (0, '学校海报'),
        (1, '学校电子屏'),
        (2, '宣传册'),
        (3, '同学交流'),
        (4, '其他（如朋友圈）'),
    )

    who_choice = (
        (0, '自己'),
        (1, '家人'),
        (2, '同学介绍'),
        (3, '辅导员推荐'),
        (4, '其他'),
    )

    Q_choice = (
        (0, '否'),
        (1, '是')

    )

    agree_choice = (
        (0, '不同意'),
        (1, '同意')
    )

    expect_sex_choice = (
        (0, '女'),
        (1, '男'),
        (2, '不介意')
    )

    # 预约基本信息
    uid = models.IntegerField(verbose_name='编号', db_index=True, unique=True)
    create_datetime = models.DateTimeField(verbose_name='创建时间', auto_now_add=True)
    # 预约者基本信息
    name = models.CharField(verbose_name='姓名', max_length=32)
    sex = models.SmallIntegerField(verbose_name='性别', choices=sex_choice)
    college = models.SmallIntegerField(verbose_name='学院', choices=college_choice)
    grade = models.SmallIntegerField(verbose_name='年级', choices=grade_choice)
    stu_code = models.CharField(verbose_name='学号/工号', max_length=12, blank=True, null=True)
    mobile_phone = models.CharField(verbose_name='手机号', max_length=32)
    email = models.EmailField(verbose_name='邮箱', max_length=32, blank=True, null=True)

    # 咨询的问题
    renji = MultiSelectField(verbose_name='人际交往', choices=renji_choice, default=0)
    qinggan = MultiSelectField(verbose_name='情感问题', choices=qinggan_choice, default=0)
    xueye = MultiSelectField(verbose_name='学业问题', choices=xueye_choice, default=0)
    zhiye = MultiSelectField(verbose_name='职业生涯', choices=zhiye_choice, default=0)
    qingxu = MultiSelectField(verbose_name='情绪问题', choices=qingxu_choice, default=0)
    xingxin = MultiSelectField(verbose_name='性心理', choices=xingxin_choice, default=0)
    abstract = models.CharField(verbose_name='情况简介', max_length=1024)

    # 危机评估
    Q1 = models.SmallIntegerField(verbose_name='是否有伤害自己或者他人的想法', choices=Q_choice, default=0)
    Q2 = models.SmallIntegerField(verbose_name='是否有伤害自己或者他人的行为', choices=Q_choice, default=0)
    Q2_1 = models.CharField(verbose_name='是什么行为', max_length=128, blank=True)
    Q3 = models.SmallIntegerField(verbose_name='有被别人伤害的可能吗', choices=Q_choice, default=0)
    Q4 = models.SmallIntegerField(verbose_name='是否服用精神类药物或喝酒', choices=Q_choice, default=0)

    # 咨询预期
    expect_sex = models.SmallIntegerField(verbose_name='您希望咨询师的性别', choices=expect_sex_choice)
    expect_age = models.SmallIntegerField(verbose_name='您希望咨询师的年龄', choices=age_choice)
    expect_time = models.CharField(verbose_name='合适的咨询时间', max_length=64)

    # 其他信息收集
    where_to_find = MultiSelectField(verbose_name='您从哪里了解心理咨询', choices=where_choice)
    who_tell_you = MultiSelectField(verbose_name='谁推荐你来做心理咨询', choices=who_choice)

    # 保密协议
    agree = models.SmallIntegerField(verbose_name='请问您是否同意', choices=agree_choice)

    class Meta:
        verbose_name_plural = "预约单"

    def __str__(self):
        return "{}号预约单".format(self.uid)


class Res_Form_Data(models.Model):
    status_choice = (
        (0, '预约未完成'),
        (1, '接待未完成'),
        (2, '已完成'),
        (3, '作废'),
        (4, '改约'),
        (5, '未验证预约')
    )

    res_form = models.ForeignKey(verbose_name='预约单', to=Reservation, on_delete=models.CASCADE,
                                 related_name='res_form')
    status = models.IntegerField(verbose_name='状态', default=0, choices=status_choice)
    filler = models.ForeignKey(verbose_name='预约填写员', to=UserInfo, on_delete=models.CASCADE, related_name='filler',
                               null=True, blank=True)
    processor = models.ForeignKey(verbose_name='预约处理员', to=UserInfo, on_delete=models.CASCADE, null=True,
                                  blank=True,
                                  default=None, related_name='processor')
    psychologist = models.CharField(verbose_name='咨询师', max_length=32, null=True, blank=True)
    comment = models.CharField(verbose_name='处理备注', max_length=256, null=True, blank=True, default=None)
    res_datetime = models.CharField(verbose_name='咨询时间', max_length=64, blank=True, null=True)
    operate_datetime = models.DateTimeField(verbose_name='操作时间', auto_now=True)

    # 满意度调查相关
    survey_code = models.CharField(verbose_name='校验码', max_length=64, unique=True, blank=True, null=True)
    invited = models.BooleanField(verbose_name="是否发送调查邀请", default=False)
    is_survey_completed = models.BooleanField(verbose_name="是否完成满意度调查", default=False)
    survey_data = models.CharField(verbose_name="调查数据", max_length=1024, blank=True, null=True)

    # 预约房间使用
    room_res = models.OneToOneField(verbose_name="咨询房间预约", to="Res_Room", blank=True, null=True,
                                    on_delete=models.SET_NULL)

    class Meta:
        verbose_name_plural = "预约状态"

    def __str__(self):
        return "{}号预约单状态：{}".format(self.res_form.uid, self.get_status_display())


class Operation(models.Model):
    ope_choice = (
        (0, '完成预约填写'),
        (1, '参与预约处理'),
        (2, '完成预约处理'),
        (3, '完成预约改约'),
        (4, '完成预约接待'),
        (5, '废弃预约'),
        (6, '添加备注'),
        (7, '参与改约处理'),
        (8, '清空预约信息'),
        (9, '验证网络预约'),
        (10, '完成续约')
    )
    operator = models.ForeignKey(verbose_name='操作人', to=UserInfo, on_delete=models.CASCADE, related_name='operator')
    ope_form = models.ForeignKey(verbose_name='预约单', to=Reservation, on_delete=models.CASCADE,
                                 related_name='ope_form')
    operation = models.SmallIntegerField(verbose_name='操作内容', choices=ope_choice)
    operate_datetime = models.DateTimeField(verbose_name='操作时间', auto_now_add=True)

    class Meta:
        verbose_name_plural = "操作记录"


Bool_choice = (
    (False, '否'),
    (True, '是')
)


class Room(models.Model):
    room_name = models.CharField(verbose_name="房间名", max_length=16, unique=True)
    describe = models.CharField(verbose_name="描述", max_length=256)
    is_for_rent = models.BooleanField(verbose_name="是否出借", choices=Bool_choice, default=True)

    class Meta:
        verbose_name_plural = "心协房间表"

    def __str__(self):
        return self.room_name


room_status_choice = (
    (0, '待审核'),
    (1, '审核通过'),
    (2, '审核不通过'),
    (3, '已取消'),
)


class Res_Room(models.Model):
    room = models.ForeignKey(verbose_name="房间", to='Room', related_name='res_room', on_delete=models.CASCADE)
    start_time = models.DateTimeField(verbose_name="使用时间")
    end_time = models.DateTimeField(verbose_name="归还时间")
    applicant = models.CharField(verbose_name="申请人/组织", max_length=16)
    reason = models.CharField(verbose_name="申请原因", max_length=256)
    person_in_charge = models.CharField(verbose_name="负责人", max_length=16)
    mobile_phone = models.CharField(verbose_name='负责人手机号', max_length=16)
    operator = models.ForeignKey(verbose_name='值班员', to=UserInfo, on_delete=models.CASCADE,
                                 related_name='room_operator')
    is_internal = models.BooleanField(verbose_name="是否为内部借用", choices=Bool_choice, default=True)
    note = models.CharField(verbose_name="备注", max_length=128, blank=True, null=True)
    status = models.SmallIntegerField(verbose_name="状态", choices=room_status_choice, default=0)
    checked_by = models.ForeignKey(verbose_name='审批人', to=UserInfo, on_delete=models.CASCADE,
                                   related_name='checked_by', blank=True, null=True)

    class Meta:
        verbose_name_plural = "房间借用记录"

    def check_time_conflict(self):
        # 如果当前预约单是审核不通过或者已取消则不检查冲突，只检查待审核和审核通过的记录
        if self.status > 1:
            return True
        # 查找结束时间晚于当前预约开始时间或开始时间早于结束时间的预约（冲突的预约）
        conflicts = Res_Room.objects.filter(
            room=self.room,
            end_time__gt=self.start_time,
            start_time__lt=self.end_time,
            status=1
        ).exclude(id=self.id).exists()
        if conflicts:
            time_list = Res_Room.objects.filter(
                room=self.room,
                end_time__gt=self.start_time,
                start_time__lt=self.end_time,
                status=1
            ).exclude(id=self.id).values_list('start_time', 'end_time')
            # 格式化时间
            time_list = ",".join([f"{s}~{e}" for s, e in time_list])
            err = {'room': '该房间在申请时间段下已被占用', 'start_time': f"时间冲突：{time_list}",
                   'end_time': f"时间冲突：{time_list}"}
            raise ValidationError(err)

        # 检查是否有重复申请
        print(type(self.start_time), self.start_time)
        duplicates = Res_Room.objects.filter(
            room=self.room,  # 检查同一房间的申请
            applicant=self.applicant,  # 检查同一申请人
            start_time__exact=self.start_time,  # 检查相同的开始时间
            end_time__exact=self.end_time,  # 检查相同的结束时间
            status=0  # 只检查状态为“待审核”的预约
        ).exclude(id=self.id).exists()  # 排除当前预约本身

        # 如果存在重复预约
        if duplicates:
            # 构造错误信息
            err = {
                'room': '已有相同申请，请勿重复提交',
                'start_time': '已有相同申请，请勿重复提交',
                'end_time': '已有相同申请，请勿重复提交'
            }

            # 抛出 ValidationError 异常，提示用户重复预约
            raise ValidationError(err)

    def clean(self):
        super().clean()

        # 提交空表单时，self不会有room等属性，直接获取会报错，因此使用getattr
        # 获取所有必要字段，获取失败则默认值为 None
        fields = ['room', 'start_time', 'end_time', 'applicant']
        field_values = {field: getattr(self, field, None) for field in fields}

        # 检查所有必要字段是否存在
        if all(field_values.values()):
            self.check_time_conflict()

    def save(self, *args, **kwargs):
        self.check_time_conflict()
        super().save(*args, **kwargs)

    def __str__(self):
        return "{} 借用者：{}".format(self.room.room_name, self.applicant)


class ResShare(models.Model):
    """ 预约情况分享 """
    consult = models.ForeignKey(verbose_name='预约单', to='Reservation', on_delete=models.CASCADE)
    code = models.CharField(verbose_name='邀请码', max_length=64, unique=True)
    count = models.PositiveIntegerField(verbose_name='限制数量', default=3, help_text='最多可查看10次')
    use_count = models.PositiveIntegerField(verbose_name='已邀请数量', default=0)
    period_choices = (
        (30, '30分钟'),
        (60, '1小时'),
        (300, '5小时'),
        (1440, '24小时'),
    )
    period = models.IntegerField(verbose_name='有效期', choices=period_choices, default=1440)
    create_datetime = models.DateTimeField(verbose_name='创建时间', auto_now_add=True)
    creator = models.ForeignKey(verbose_name='分享创建者', to='UserInfo', related_name='create_invite', on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "分享码"

    def __str__(self):
        return "%s号预约单的分享码" % self.consult.uid


class UserSurvey(models.Model):
    user = models.ForeignKey(verbose_name='测试者', to='UserInfo', related_name='survey', on_delete=models.CASCADE)
    create_datetime = models.DateTimeField(verbose_name='测试时间', auto_now_add=True)
    result = models.TextField(verbose_name="测试结果")
    survey = models.CharField(verbose_name="项目名", max_length=32)

    class Meta:
        verbose_name_plural = "量表测试结果"

    def __str__(self):
        return "{} 的 {} 结果".format(self.user.username, self.survey)


class Psychologist(models.Model):
    college_choice = (
        (0, '商船'),
        (1, '交运'),
        (2, '经管'),
        (3, '物流'),
        (4, '信息'),
        (5, '外语'),
        (6, '文理'),
        (7, '法学院'),
        (8, '海科'),
        (9, '其他'),
        (10, '专职老师'),
    )

    sex_choice = (
        (0, '女'),
        (1, '男'),
    )

    age_choice = (
        (0, '20-30'),
        (1, '30-40'),
        (2, '40以上'),
        (3, '未设置'),
    )

    name = models.CharField(verbose_name='咨询师姓名', max_length=16)
    age = models.SmallIntegerField(verbose_name='年龄', choices=age_choice, default=3)
    sex = models.SmallIntegerField(verbose_name='性别', choices=sex_choice)
    mobile_phone = models.CharField(verbose_name='手机号', max_length=32, unique=True)
    college = models.SmallIntegerField(verbose_name='所属单位', choices=college_choice)
    expertise = models.CharField(verbose_name='擅长领域', max_length=64, blank=True, null=True)
    available_time = models.CharField(verbose_name='可咨询时间', max_length=32)
    notes = models.CharField(verbose_name="备注", max_length=256, blank=True, null=True)

    class Meta:
        verbose_name_plural = "咨询师名单"


class Pusher(models.Model):
    content_type_choice = (
        (1, '文字'),
        (2, 'html'),
        (3, 'markdown'),
    )

    name = models.CharField(verbose_name="推送名称", max_length=64, unique=True)
    receiver = models.CharField(verbose_name="接收者", default="[]", max_length=1024)
    summary = models.CharField(verbose_name="推送摘要", max_length=128)
    content = models.CharField(verbose_name="正文", max_length=1024)
    redirect = models.CharField(verbose_name="URL链接", max_length=128, blank=True, default="")
    content_type = models.SmallIntegerField(verbose_name="正文类型", choices=content_type_choice, default=2)

    class Meta:
        verbose_name_plural = "微信提醒推送"

    def __str__(self):
        return self.name

    @property
    def receiver_list(self):
        """
        获取订阅者uid列表
        @return: list|None
        """
        try:
            receiver_list = json.loads(self.receiver)
        except json.JSONDecodeError:
            # 处理 JSON 解码错误，则返回None
            receiver_list = None
        return receiver_list

    def add_receiver(self, receiver: str):
        """
        添加receiver进入列表
        @param receiver: uid字符串
        @return:
        """
        if not isinstance(receiver, str):
            raise TypeError("receiver must be str!")
        # 反序列化存储的 JSON 字符串为 Python 对象
        existing_list: list = json.loads(self.receiver)

        # 添加新内容到列表
        existing_list.append(receiver)

        # 序列化列表为 JSON 字符串，并存储到文本字段中
        self.receiver = json.dumps(existing_list)
        self.save()

    def del_receiver(self, receiver: str):
        """
        删除receiver中的元素
        @rtype: object
        @param receiver: uid字符串
        @return:
        """
        if not isinstance(receiver, str):
            raise TypeError("receiver must be str!")
        # 反序列化存储的 JSON 字符串为 Python 对象
        existing_list: list = json.loads(self.receiver)

        # 如果receiver在列表中，则删除该元素
        if receiver in existing_list:
            existing_list.remove(receiver)
        else:
            raise ValueError(f'{receiver} not in receiver list')

        # 序列化列表为 JSON 字符串，并存储到文本字段中
        self.receiver = json.dumps(existing_list)
        self.save()

    def clear_receiver(self):
        """
        清除所有的receiver
        @return:
        """
        self.receiver = json.dumps([])
        self.save()
        return True


# 按摩椅使用历史记录
class MassageUseHistory(models.Model):
    user = models.ForeignKey(verbose_name='用户', to='UserInfo', related_name='massage_use_history',
                             on_delete=models.PROTECT)
    device_id = models.CharField(verbose_name='设备ID', max_length=64)
    operation_type = models.CharField(verbose_name='操作类型', max_length=64)
    operation_time = models.DateTimeField(verbose_name='操作时间', auto_now_add=True)

    class Meta:
        verbose_name_plural = "按摩椅使用历史记录"

    def __str__(self):
        return f"{self.user.username} 使用 {self.device_id} 在 {self.operation_time} 操作 {self.operation_type}"


# ===========================================================================
# 冥想室预约模块
#
# 与心理预约模块（Reservation / Res_Form_Data / Operation / ResShare）保持同构，
# 便于页面与处理流程"照搬"。刻意保持独立建表而非复用，原因：
#   1. 操作历史接口 api_history 是全局扫 Operation 表的，共用会串数据；
#   2. 状态机语义虽然相同，但业务字段差异大（无危机评估/咨询师/问题分类）。
# 唯一的架构性差异：冥想室**不接 Res_Room 房间审批**。
#   Res_Room 的语义是"整间房排他借用"，而冥想室是"单房间内 17 个座位并行使用"，
#   粒度不同；复用会导致"一人预约即整室被占"。占用关系由 (res_date, slot, seat)
#   三元组表达即可。
# ===========================================================================

# 预约单来源
meditation_source_choice = (
    (0, '微信小程序'),
    (1, '平台代录'),
    (2, '现场登记'),
    (3, '网页预约'),   # 公众号菜单 / 二维码进入的对外网页
)

# 状态机（与 Res_Form_Data.status_choice 完全一致，便于照搬处理流程）
meditation_status_choice = (
    (0, '预约未完成'),
    (1, '接待未完成'),
    (2, '已完成'),
    (3, '作废'),
    (4, '改约'),
    (5, '未验证预约'),
)

# 操作类型（在心理预约 0-10 的基础上，按冥想室语境改写，并扩展 11-13）
meditation_ope_choice = (
    (0, '完成冥想室预约填写'),
    (1, '参与冥想室预约处理'),
    (2, '完成冥想室预约受理'),
    (3, '完成冥想室改约'),
    (4, '完成签到接待'),
    (5, '废弃冥想室预约'),
    (6, '添加备注'),
    (7, '参与改约处理'),
    (8, '清空预约信息'),
    (9, '验证小程序预约'),
    (10, '完成续约'),
    (11, '完成签退'),
    (12, '标记爽约'),
    (13, '标记超时'),
)

# 哪些状态视为"仍占用座位"：
#   0 预约未完成     —— 已受理，占座
#   1 接待未完成     —— 待到访，占座
#   4 改约           —— 占座
#   5 未验证预约     —— **必须占座**
# 2 已完成、3 作废 释放座位。
#
# 关于 5（未验证）为何要占座：小程序提交后会立刻向学生回显"预约成功 + 单号"，
# 学生认为座位已是自己的。若此时不计占用，两个人可同时预约同一座位、
# 双方都收到成功回执，直到值班员受理时才发现冲突 —— 这是错误的用户体验。
# 代价是恶意/误提交能短暂占座，由「同手机号防重复」「值班员验证/废弃」兜底。
MEDITATION_ACTIVE_STATUS = (0, 1, 4, 5)


class Med_Reservation(models.Model):
    '''冥想室预约单'''

    # 预约基本信息
    uid = models.IntegerField(verbose_name='编号', db_index=True, unique=True)
    create_datetime = models.DateTimeField(verbose_name='创建时间', auto_now_add=True)

    # 预约者基本信息（与心理预约一致的通用字段）
    name = models.CharField(verbose_name='姓名', max_length=32)
    sex = models.SmallIntegerField(verbose_name='性别', choices=Reservation.sex_choice)
    college = models.SmallIntegerField(verbose_name='学院', choices=college_choice)
    grade = models.SmallIntegerField(verbose_name='年级', choices=Reservation.grade_choice)
    stu_code = models.CharField(verbose_name='学号/工号', max_length=12, blank=True, null=True)
    mobile_phone = models.CharField(verbose_name='手机号', max_length=32, db_index=True)
    email = models.EmailField(verbose_name='邮箱', max_length=32, blank=True, null=True)

    # 冥想室专属：资源由 (日期, 时段, 座位) 三元组唯一确定
    res_date = models.DateField(verbose_name='使用日期', db_index=True)
    slot = models.SmallIntegerField(verbose_name='使用时段', choices=MEDITATION_SLOTS)
    seat = models.SmallIntegerField(verbose_name='座位号', choices=MEDITATION_SEAT_CHOICES)

    # 使用诉求 / 备注（对应心理预约的 abstract）
    note = models.CharField(verbose_name='备注', max_length=1024, blank=True)
    agree = models.SmallIntegerField(verbose_name='是否已阅读并同意《须知与承诺》',
                                     choices=Reservation.agree_choice, default=1)

    # 来源溯源（小程序预约需能追回是哪一端提交的）
    source = models.SmallIntegerField(verbose_name='预约来源', choices=meditation_source_choice, default=1)
    wx_openid = models.CharField(verbose_name='微信openid', max_length=64, null=True, blank=True, db_index=True)
    read_seconds = models.SmallIntegerField(verbose_name='须知阅读时长(秒)', default=0)

    # 现场签到 / 签退（docx：须提前 5 分钟到值班室纸质签到，离场纸质签退）
    checkin_datetime = models.DateTimeField(verbose_name='签到时间', null=True, blank=True)
    checkout_datetime = models.DateTimeField(verbose_name='签退时间', null=True, blank=True)

    # 违约标记（本期只建字段，黑名单统计逻辑待值班表确定后再接线）
    no_show = models.BooleanField(verbose_name='是否爽约', default=False)
    overdue = models.BooleanField(verbose_name='是否超时', default=False)

    class Meta:
        verbose_name_plural = "冥想室预约单"
        # 选座图/占用查询都按这三个字段过滤，建复合索引
        indexes = [models.Index(fields=['res_date', 'slot', 'seat'])]

    def __str__(self):
        return "{}号冥想室预约单".format(self.uid)

    # ---------------------------------------------------------------
    # 座位占用查询
    # ---------------------------------------------------------------
    @classmethod
    def is_seat_taken(cls, res_date, slot, seat, exclude_uid=None):
        """(日期, 时段, 座位) 是否已被占用。

        exclude_uid 用于改约场景：改约时本单自身不应算作冲突。
        """
        qs = cls.objects.filter(
            res_date=res_date, slot=slot, seat=seat,
            res_form__status__in=MEDITATION_ACTIVE_STATUS,
        )
        if exclude_uid is not None:
            qs = qs.exclude(uid=exclude_uid)
        return qs.exists()

    @classmethod
    def taken_seats(cls, res_date, slot=None):
        """一次性取出某日期（可选某时段）下所有已占用的座位。

        返回 [(slot, seat), ...]，供选座图染色。用 values_list 避免把整行
        对象取回来，也避免在模板里逐座位发查询（N+1）。
        """
        qs = cls.objects.filter(
            res_date=res_date, res_form__status__in=MEDITATION_ACTIVE_STATUS,
        )
        if slot is not None:
            qs = qs.filter(slot=slot)
        return list(qs.values_list('slot', 'seat'))

    def seat_display_short(self):
        """给列表/周历用的紧凑展示，形如 '10/15 14:00-14:40 · 7号座'。"""
        from web.meditation_constants import slot_label
        label = slot_label(self.slot)
        date_part = self.res_date.strftime('%m/%d') if self.res_date else '--'
        return "{} {} · {}号座".format(date_part, label, self.seat)


class Med_Form_Data(models.Model):
    '''冥想室预约状态（状态机，与 Res_Form_Data 同构）'''

    res_form = models.ForeignKey(verbose_name='冥想室预约单', to=Med_Reservation,
                                 on_delete=models.CASCADE, related_name='res_form')
    status = models.IntegerField(verbose_name='状态', default=0, choices=meditation_status_choice)
    filler = models.ForeignKey(verbose_name='预约填写员', to=UserInfo, on_delete=models.CASCADE,
                               related_name='med_filler', null=True, blank=True)
    processor = models.ForeignKey(verbose_name='预约处理员', to=UserInfo, on_delete=models.CASCADE,
                                  null=True, blank=True, default=None, related_name='med_processor')
    # 对应心理预约的 psychologist（咨询师）；冥想室改为值班引导员
    guide = models.CharField(verbose_name='值班引导员', max_length=32, null=True, blank=True)
    comment = models.CharField(verbose_name='处理备注', max_length=256, null=True, blank=True, default=None)
    # 反规范化的"日期+时段"展示串，如 '2026-10-15 8:20-9:00'。
    # 保留该字段是为了让周历/打印/调查页能几乎原样复用心理预约的实现。
    res_datetime = models.CharField(verbose_name='预约时间', max_length=64, blank=True, null=True)
    operate_datetime = models.DateTimeField(verbose_name='操作时间', auto_now=True)

    # 满意度调查相关（原样照搬心理预约的机制）
    survey_code = models.CharField(verbose_name='校验码', max_length=64, unique=True, blank=True, null=True)
    invited = models.BooleanField(verbose_name="是否发送调查邀请", default=False)
    is_survey_completed = models.BooleanField(verbose_name="是否完成满意度调查", default=False)
    survey_data = models.CharField(verbose_name="调查数据", max_length=1024, blank=True, null=True)

    class Meta:
        verbose_name_plural = "冥想室预约状态"

    def __str__(self):
        return "{}号冥想室预约单状态：{}".format(self.res_form.uid, self.get_status_display())


class Med_Operation(models.Model):
    '''冥想室操作记录

    独立建表（不复用 Operation）：心理预约的 api_history / api_check_statistics
    是全局扫 Operation 表的，若共用会让两个模块的操作历史互相污染。
    '''

    operator = models.ForeignKey(verbose_name='操作人', to=UserInfo, on_delete=models.CASCADE,
                                 related_name='med_operator')
    ope_form = models.ForeignKey(verbose_name='冥想室预约单', to=Med_Reservation,
                                 on_delete=models.CASCADE, related_name='ope_form')
    operation = models.SmallIntegerField(verbose_name='操作内容', choices=meditation_ope_choice)
    operate_datetime = models.DateTimeField(verbose_name='操作时间', auto_now_add=True)

    class Meta:
        verbose_name_plural = "冥想室操作记录"
        ordering = ['-id']

    def __str__(self):
        return "{} 在 {} 对 {} 号单操作：{}".format(
            self.operator.username,
            self.operate_datetime.strftime('%Y-%m-%d %H:%M'),
            self.ope_form.uid,
            self.get_operation_display(),
        )


class Med_Share(models.Model):
    '''冥想室预约情况分享（与 ResShare 同构）'''

    consult = models.ForeignKey(verbose_name='冥想室预约单', to=Med_Reservation,
                                on_delete=models.CASCADE, related_name='med_share')
    code = models.CharField(verbose_name='邀请码', max_length=64, unique=True)
    count = models.PositiveIntegerField(verbose_name='限制数量', default=3, help_text='最多可查看10次')
    use_count = models.PositiveIntegerField(verbose_name='已邀请数量', default=0)
    period_choices = (
        (30, '30分钟'),
        (60, '1小时'),
        (300, '5小时'),
        (1440, '24小时'),
    )
    period = models.IntegerField(verbose_name='有效期', choices=period_choices, default=1440)
    create_datetime = models.DateTimeField(verbose_name='创建时间', auto_now_add=True)
    creator = models.ForeignKey(verbose_name='分享创建者', to=UserInfo,
                                related_name='med_create_invite', on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = "冥想室分享码"

    def __str__(self):
        return "%s号冥想室预约单的分享码" % self.consult.uid


class Med_Blacklist(models.Model):
    '''冥想室黑名单

    本期**只建表不接线**：docx 规定"累计 3 次爽约或超时进黑名单，一周后自动解禁"，
    但该规则依赖"值班在岗时段表"，暂未确定，故先留结构，统计逻辑后续再接。
    '''

    stu_code = models.CharField(verbose_name='学号/工号', max_length=12, unique=True, db_index=True)
    mobile_phone = models.CharField(verbose_name='手机号', max_length=32, blank=True, null=True)
    reason = models.CharField(verbose_name='加入原因', max_length=128, blank=True)
    strike_count = models.SmallIntegerField(verbose_name='累计违约次数', default=0)
    locked_until = models.DateTimeField(verbose_name='解禁时间')
    create_datetime = models.DateTimeField(verbose_name='创建时间', auto_now_add=True)

    class Meta:
        verbose_name_plural = "冥想室黑名单"

    def __str__(self):
        return "{}（{}次违约，解禁于{}）".format(
            self.stu_code, self.strike_count, self.locked_until.strftime('%Y-%m-%d %H:%M'))
