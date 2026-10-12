"""gzpt URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from web.views import account, reservation, notification, room, datashow, beta, pusher, meditation, meditation_api

urlpatterns = [
    url(r'^index/', account.index, name='index'),

    # 用户
    url(r'^register/$', account.register, name='register'),  # 首页
    url(r'^login/$', account.login, name='login'),  # 登陆
    url(r'^send/email/$', account.send_email, name='send_email'),  # 邮件验证码发送
    url(r'^image/code/$', account.image_code, name='image_code'),  # 验证码图片
    url(r'^logout/$', account.logout, name='logout'),  # 登出
    url(r'^export/excel/(?P<obj>\w+)/$', account.export_excel, name='export_excel'),  # 输入excel
    url(r'^init/data/visible/$', account.init_data_visible, name='init_data_visible'),  # 初始化数据
    url(r'^find/password/$', account.find_password, name='find_password'),  # 找回密码
    url(r'^find/change/password/(?P<user_id>\d+)/$', account.find_change_password, name='find_change_password'),  # 修改密码
    url(r'^send/email/find/$', account.send_email_find, name='send_email_find'),  # 找回密码-发送验证码邮件
    url(r'^login/monitor/$', account.login_monitor, name='login_monitor'),  # 登陆信息监控
    url(r'^advise/$', account.advise_to_email, name='advise_to_email'),  # 发送建议到邮箱

    # 通知
    url(r'^add/notification/$', notification.add_notification, name='add_notification'),  # 发布通知
    url(r'^edit/notification/(?P<id>\d+)/$', notification.edit_notification, name='edit_notification'),  # 编辑通知
    url(r'^detail/notification/(?P<id>\d+)/$', notification.detail_notification, name='detail_notification'),  # 查看通知
    url(r'^notification/list/$', notification.notification_list, name='notification_list'),  # 通知列表
    url(r'^delete/notification/(?P<id>\d+)/$', notification.delete_notification, name='delete_notification'),  # 删除通知

    # 成员管理
    url(r'^check/newmember/(?P<request_id>\d+)/$', account.check_newmember, name='check_newmember'),  # 注册允许
    url(r'^edit/member/$', account.edit_member, name='edit_member'),  # 编辑成员信息
    url(r'^export/excel/(?P<obj>\w+)/$', account.export_excel, name='export_excel'),  # 输出excel
    url(r'^all/member/$', account.all_member, name='all_member'),  # 查看本部门用户
    url(r'^all/all/member/$', account.all_all_member, name='all_all_member'),  # 查看全部用户
    url(r'^edit/userinfo/$', account.edit_userinfo, name='edit_userinfo'),  # 用户修改本人信息
    url(r'^delete/all/$', account.delete_all, name='delete_all'),  # 把除了指导老师外的所有用户变成往届用户

    # 预约单
    url(r'^dashboard/$', account.dashboard, name='dashboard'),  # 平台主页
    url(r'^new/reservation/$', reservation.new_reservation, name='new_reservation'),  # 新预约填写
    url(r'^reservation/list/$', reservation.reservation_list, name='reservation_list'),  # 所有预约列表
    url('reservation/detail/(?P<uid>\d+)/$', reservation.reservation_detail, name='reservation_detail'),  # 预约详情/处理
    url('reservation/print/(?P<uid>\d+)/$', reservation.print_reservation, name='print_reservation'),  # 打印预约单
    url('reservation/appoint/list/$', reservation.reservation_appoint_list, name='reservation_appoint_list'),  # 预约未完成列表
    url('reservation/receive/list/$', reservation.reservation_receive_list, name='reservation_receive_list'),  # 接待未完成列表
    url(r'^calendar/$', reservation.calendar, name='calendar'),  # 预约周历
    url(r'consultation/appointment/$', reservation.consultation_appointment, name='consultation_appointment'),
    url(r'^reservation/wps/$', reservation.reservation_wps, name='reservation_wps'),
    # 咨询预约-对外
    url(r'^res/share/code/(?P<res_id>\d+)/$', reservation.res_share_code, name='res_share_code'),  # 分享预约
    url(r'^share/visit/(?P<code>\w+)/$', reservation.share_visit, name='share_visit'),  # 访问预约分享
    # 预约咨询-操作历史
    url(r'^operate/history/$', reservation.operate_history, name='operate_history'),  # 操作历史
    url(r'^api/history/$', reservation.api_history, name='api_history'),  # 获取操作历史
    url(r'^api/check/statistics$', reservation.api_check_statistics, name='api_check_statistics'),  # 统计操作类型
    # 咨询调查反馈
    url(r'^survey/(?P<res_id>\d+)/(?P<code>\w+)/$', reservation.survey, name='reservation_survey'),
    url(r'^send/survey/(?P<res_id>\d+)/$', reservation.send_survey, name='send_survey'),
    url(r'^api/survey/data/(?P<key>\w+)/$', reservation.survey_api_output, name='survey_api_output'),

    # 房间管理
    url(r'^room/list/$', room.room_list, name='room_list'),  # 房间列表
    url(r'^room/detail/(?P<name>\w+)/$', room.room_detail, name='room_detail'),  # 房间详情
    url(r'^init/res/list/(?P<day>\d+)/(?P<name>\w+)/$', room.init_res_list, name='init_res_list'),  # 初始化近期预约记录
    url(r'^res/detail/(?P<id>\d+)/$', room.res_detail, name='res_detail'),  # 房间预约详情
    url(r'^download/res/room/$', room.download_res_room, name='download_res_room'),  # 下载房间借用表
    url(r'^room/check/list/$', room.room_check_list, name='room_check_list'),  # 房间审批列表
    url(r'^room/check/$', room.room_check, name='room_check'),  # 房间审批
    url(r'^get/room/qrcode/$', room.get_room_qrcode, name='get_room_qrcode'),  # wx pusher获取房间通知的关注二维码
    url(r'^room/res/list/$', room.room_res_list, name='room_res_list'),  # 房间借用记录列表

    # 数据大屏
    url(r'^data/display/$', datashow.data_display, name='data_display'),  # 大屏主页
    url(r'^api/data/(?P<name>\w+)/$', datashow.get_data, name='get_data'),  # 数据获取

    # beta实验室
    url(r'^beta/$', beta.beta_index, name='beta_index'),  # 实验室主页
    url(r'^beta/esurvey/index/$', beta.esurvey_index, name='esurvey_index'),  # 量表生成器主页
    url(r'^beta/esurvey/scl90/$', beta.esurvey_scl90, name='esurvey_scl90'),  # esurvey_scl90
    url(r'^beta/esurvey/sas/$', beta.esurvey_sas, name='esurvey_sas'),  # esurvey_sas
    url(r'^beta/esurvey/sds/$', beta.esurvey_sds, name='esurvey_sds'),  # esurvey_sds
    url(r'^beta/esurvey/qsa/$', beta.esurvey_qsa, name='esurvey_qsa'),  # esurvey_qsa

    # 按摩
    url(r'^massage/index/$', beta.massage_index, name='massage_index'),  # 按摩主页
    url(r'^massage/control/$', beta.massage_control, name='massage_control'),  # 按摩控制
    url(r'^massage/history/$', beta.massage_history, name='massage_history'),  # 按摩使用记录页面
    url(r'^massage/history/api/$', beta.massage_history_api, name='massage_history_api'),  # 按摩记录API接口

    # wx_pusher
    url(r'^get/qrcode/(?P<pusher_id>\d+)/$', pusher.get_qrcode, name='get_qrcode'),  # wx pusher获取通知的关注二维码
    url(r'^bind/receiver/$', pusher.bind_receiver, name='bind_receiver'),  # 绑定通知的uid
    # wx_pusher_解绑通知的uid
    url(r'^remove/receiver/(?P<pusher_id>\d+)/(?P<uid>\w+)/$', pusher.remove_receiver, name='remove_receiver'),
    # pusher管理页面
    url(r'^pusher/list/$', pusher.pusher_list, name='pusher_list'),  # pusher列表页面
    url(r'^pusher/detail/(?P<pusher_id>\d+)/$', pusher.pusher_detail, name='pusher_detail'),  # pusher详情页面
    url(r'^pusher/clear/(?P<pusher_id>\d+)/$', pusher.clear_all_receivers, name='clear_all_receivers'),  # 清空所有订阅者

    url(r'^$', account.index),  # 默认跳转index

    # ==================== 冥想室预约 ====================
    # 平台端（需登录；具体权限在视图内判断）
    url(r'^meditation/new/$', meditation.new_meditation, name='new_meditation'),  # 代录填写
    url(r'^meditation/list/$', meditation.meditation_list, name='meditation_list'),  # 所有预约单
    url(r'^meditation/appoint/list/$', meditation.meditation_appoint_list,
        name='meditation_appoint_list'),  # 待受理
    url(r'^meditation/receive/list/$', meditation.meditation_receive_list,
        name='meditation_receive_list'),  # 待到访
    url(r'^meditation/detail/(?P<uid>\d+)/$', meditation.meditation_detail,
        name='meditation_detail'),  # 详情/处理
    url(r'^meditation/print/(?P<uid>\d+)/$', meditation.print_meditation,
        name='print_meditation'),  # 打印
    url(r'^meditation/calendar/$', meditation.meditation_calendar, name='meditation_calendar'),  # 周历
    url(r'^meditation/selection/$', meditation.meditation_selection,
        name='meditation_selection'),  # 选座总览
    url(r'^meditation/operate/history/$', meditation.med_operate_history,
        name='med_operate_history'),  # 操作历史
    url(r'^meditation/api/history/$', meditation.med_api_history, name='med_api_history'),
    url(r'^meditation/api/check/statistics$', meditation.med_api_check_statistics,
        name='med_api_check_statistics'),
    url(r'^meditation/api/seat/map/$', meditation.meditation_seat_map_api,
        name='meditation_seat_map_api'),  # 座位占用（平台端与小程序共用）

    # 分享码
    url(r'^meditation/share/code/(?P<res_id>\d+)/$', meditation.med_share_code,
        name='med_share_code'),
    url(r'^meditation/share/visit/(?P<code>\w+)/$', meditation.med_share_visit,
        name='med_share_visit'),  # 公开

    # 满意度调查
    url(r'^meditation/survey/(?P<res_id>\d+)/(?P<code>\w+)/$', meditation.meditation_survey,
        name='meditation_survey'),  # 公开（凭 code）
    url(r'^meditation/send/survey/(?P<res_id>\d+)/$', meditation.send_meditation_survey,
        name='send_meditation_survey'),
    url(r'^meditation/api/survey/data/(?P<key>\w+)/$', meditation.med_survey_api_output,
        name='med_survey_api_output'),

    # 冥想室 —— 对外接口（公开）
    # 同学预约页面**不在本平台**：它托管在另一个域名上，跨域调用这里的接口。
    # 跨域放行由 web/middleware/meditation_cors.py 处理，
    # 允许来源在 settings.MEDITATION_CORS_ORIGINS 配置。
    url(r'^meditation/api/wxlogin/$', meditation_api.wx_login, name='med_api_wxlogin'),
    url(r'^meditation/api/layout/$', meditation_api.layout, name='med_api_layout'),
    url(r'^meditation/api/notice/$', meditation_api.notice, name='med_api_notice'),
    url(r'^meditation/api/slots/$', meditation_api.slots, name='med_api_slots'),
    url(r'^meditation/api/submit/$', meditation_api.submit, name='med_api_submit'),
    url(r'^meditation/api/mpl/list/$', meditation_api.my_list, name='med_api_mpl_list'),
    url(r'^meditation/api/cancel/$', meditation_api.cancel, name='med_api_cancel'),
    url(r'^meditation/api/reschedule/$', meditation_api.reschedule, name='med_api_reschedule'),
]
