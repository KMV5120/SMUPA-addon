from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from web.models import *


class IsWXUIDBindFilter(admin.SimpleListFilter):
    title = _('是否绑定微信')  # 在 admin 中显示的标题
    parameter_name = 'wx_uid_bind'  # URL 中使用的参数名称

    def lookups(self, request, model_admin):
        return (
            ('1', _('未绑定')),
            ('0', _('绑定')),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(wx_uid__isnull=True)
        if self.value() == '0':
            return queryset.filter(wx_uid__isnull=False)


class IsActiveUserFilter(admin.SimpleListFilter):
    title = _('是否激活')
    parameter_name = 'is_active_user'

    def lookups(self, request, model_admin):
        """
        定义过滤选项
        """
        return [
            ('active', '激活'),
            ('inactive', '未激活'),
        ]

    def queryset(self, request, queryset):
        """
        根据选择过滤查询集
        """
        if self.value() == 'active':
            return queryset.filter(user_type__gt=0)
        elif self.value() == 'inactive':
            return queryset.filter(user_type=0)
        return queryset


# Register your models here.
class admin_Reservation(admin.ModelAdmin):
    list_display = ('uid', 'create_datetime', 'name', 'sex', 'stu_code', 'college', 'grade')
    search_fields = ('uid', 'name', 'stu_code')
    list_filter = ('sex', 'college', 'grade')
    ordering = ('uid',)


class admin_UserInfo(admin.ModelAdmin):
    ordering = ['is_locked', '-user_type']
    exclude = ('password',)
    list_display = ('username', 'apartment', 'user_type', 'stu_code', 'mobile_phone', 'email', 'college', 'class_name')
    search_fields = ('username', 'college', 'stu_code')
    list_filter = ('college', 'apartment', 'user_type', 'is_locked', IsWXUIDBindFilter, IsActiveUserFilter)


class admin_Res_Room(admin.ModelAdmin):
    list_display = ('applicant', 'room', 'start_time', 'end_time', 'reason', 'is_internal', 'status', 'checked_by')


class admin_Operation(admin.ModelAdmin):
    list_display = ('operator', 'ope_form', 'operation', 'operate_datetime')


class admin_Room(admin.ModelAdmin):
    list_display = ('room_name', 'describe', 'is_for_rent')


class admin_UserSurvey(admin.ModelAdmin):
    readonly_fields = ('user', 'survey', 'result', 'create_datetime')
    list_display = ('user', 'survey', 'create_datetime')
    list_filter = ('user', 'survey')


class admin_Psychologist(admin.ModelAdmin):
    list_display = ('name', 'age', 'sex', 'mobile_phone', 'college', 'expertise', 'available_time', 'notes')
    list_filter = ('name', 'age', 'sex', 'mobile_phone', 'college')


class admin_Res_Form_Data(admin.ModelAdmin):
    list_filter = ('status', 'invited', 'is_survey_completed')


class admin_Pusher(admin.ModelAdmin):
    list_display = ('id', 'name', 'summary', 'receiver')


class admin_MassageUseHistory(admin.ModelAdmin):
    list_display = ('user', 'device_id', 'operation_type', 'operation_time')
    list_filter = ('device_id', 'operation_type', 'operation_time')
    search_fields = ('user__username', 'user__stu_code', 'device_id')
    readonly_fields = ('operation_time',)
    ordering = ('-operation_time',)
    date_hierarchy = 'operation_time'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')


class admin_Med_Reservation(admin.ModelAdmin):
    list_display = ('uid', 'create_datetime', 'name', 'sex', 'res_date', 'slot', 'seat',
                    'mobile_phone', 'source')
    search_fields = ('uid', 'name', 'stu_code', 'mobile_phone', 'wx_openid')
    list_filter = ('sex', 'college', 'grade', 'source', 'res_date', 'slot', 'seat')
    ordering = ('-uid',)
    date_hierarchy = 'res_date'
    readonly_fields = ('create_datetime',)


class admin_Med_Form_Data(admin.ModelAdmin):
    list_display = ('res_form', 'status', 'guide', 'filler', 'processor', 'operate_datetime')
    list_filter = ('status', 'invited', 'is_survey_completed')
    search_fields = ('res_form__uid', 'res_form__name', 'guide')


class admin_Med_Operation(admin.ModelAdmin):
    list_display = ('operator', 'ope_form', 'operation', 'operate_datetime')
    list_filter = ('operation',)
    search_fields = ('operator__username', 'ope_form__uid')
    ordering = ('-id',)
    date_hierarchy = 'operate_datetime'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('operator', 'ope_form')


class admin_Med_Share(admin.ModelAdmin):
    list_display = ('consult', 'code', 'count', 'use_count', 'period', 'creator', 'create_datetime')
    search_fields = ('code', 'consult__uid')


class admin_Med_Blacklist(admin.ModelAdmin):
    list_display = ('stu_code', 'mobile_phone', 'strike_count', 'locked_until', 'reason', 'create_datetime')
    search_fields = ('stu_code', 'mobile_phone')
    ordering = ('-create_datetime',)


admin.site.site_header = 'SMUPA工作平台｜后台'
admin.site.site_title = "SMUPA工作平台｜后台"
admin.site.index_title = "后台主页"
admin.site.register(UserInfo, admin_UserInfo)
admin.site.register(Res_Form_Data, admin_Res_Form_Data)
admin.site.register(Reservation, admin_Reservation)
admin.site.register(Room, admin_Room)
admin.site.register(Res_Room, admin_Res_Room)
admin.site.register(Notification)
admin.site.register(LoginTime)
admin.site.register(ResShare)
admin.site.register(Operation, admin_Operation)
admin.site.register(UserSurvey, admin_UserSurvey)
admin.site.register(Psychologist, admin_Psychologist)
admin.site.register(Pusher, admin_Pusher)
admin.site.register(MassageUseHistory, admin_MassageUseHistory)

# 冥想室预约
admin.site.register(Med_Reservation, admin_Med_Reservation)
admin.site.register(Med_Form_Data, admin_Med_Form_Data)
admin.site.register(Med_Operation, admin_Med_Operation)
admin.site.register(Med_Share, admin_Med_Share)
admin.site.register(Med_Blacklist, admin_Med_Blacklist)
