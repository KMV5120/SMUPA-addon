# -*- coding: utf-8 -*-
import datetime
import json
import traceback
from typing import List

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, QueryDict
from django.shortcuts import render, reverse
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings
from utils.SMTP import send_email
from utils.encrypt import init_code
from utils.model_utils import get_field_name_by_verbose_name, get_choice_key_or_original_value, \
    get_multi_choice_extra_value
from utils.validate_tools import validate_datetime_format
from utils.wx_pusher import send_pusher_by_id
from web import models
from web.forms.roomForms import RoomListForm, RoomBookForm
from web.forms.reservationForm import NewReservationForm, InviteModelForm, ReservationSurveyForm, \
    NewReservationInviteForm


def new_reservation(request):
    if request.method == "GET":
        try:
            uid = models.Reservation.objects.last().uid + 1  # 读取最后一单的uid，并得出新预约单的uid
        except AttributeError:
            uid = 1
        return render(request, 'reservation/new_reservation.html', locals())

    '''POST请求则验证表单'''
    form = NewReservationForm(request, data=request.POST)
    if form.is_valid():  # 判断表单是否有效
        instance = form.save()  # 保存预约单
        staff = form.cleaned_data['staff']
        if staff:  # 若有其他值班员则为其他值班员添加工作记录
            operations = []
            for staff_member in staff.split():
                staff_user = models.UserInfo.objects.get(username=staff_member, is_locked=False)  # 获取 UserInfo 实例
                operations.append(models.Operation(
                    operator=staff_user,
                    ope_form=instance,
                    operation=0,
                ))
            models.Operation.objects.bulk_create(operations)  # 批量插入
        # 修改预约单状态
        models.Res_Form_Data.objects.create(
            res_form=instance,
            filler=request.STAFF.user,
            processor=None,
            comment=None
        )
        # 添加登陆账户的工作记录
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=0,
        )
        return JsonResponse({'status': True})
    return JsonResponse({'status': False, 'error': form.errors})


def reservation_list(request):
    if request.GET.get("search"):
        query = request.GET.get('search')
        print(type(query))
        all_res = models.Reservation.objects.filter(
            Q(name__contains=query) | Q(mobile_phone=query) | Q(email=query) | Q(stu_code=query) | Q(
                abstract__contains=query) | Q(res_form__psychologist__contains=query)).all().order_by(
            'uid')
    else:
        all_res = models.Reservation.objects.all().order_by('uid')
    pages = request.GET.get('page')
    lists = Paginator(all_res, 10)
    try:
        res_list = lists.page(pages)
    except EmptyPage:
        res_list = lists.page(lists.num_pages)
    except PageNotAnInteger:
        res_list = lists.page(1)

    return render(request, 'reservation/reservation_list.html', locals())


def reservation_appoint_list(request):
    if request.GET.get("search"):
        query = request.GET.get('search')
        print(type(query))
        all_res = models.Reservation.objects.filter(res_form__status=0).all().filter(
            Q(name__contains=query) | Q(mobile_phone=query) | Q(email=query) | Q(stu_code=query) | Q(
                abstract__contains=query) | Q(res_form__psychologist__contains=query)).all().order_by(
            'uid')
    else:
        all_res = models.Reservation.objects.filter(res_form__status=0).all().order_by('uid')
    pages = request.GET.get('page')
    lists = Paginator(all_res, 10)
    try:
        res_list = lists.page(pages)
    except EmptyPage:
        res_list = lists.page(lists.num_pages)
    except PageNotAnInteger:
        res_list = lists.page(1)

    return render(request, 'reservation/reservation_appoint_list.html', locals())


def reservation_receive_list(request):
    if request.GET.get("search"):
        query = request.GET.get('search')
        print(type(query))
        all_res = models.Reservation.objects.filter(res_form__status=1).all().filter(
            Q(name__contains=query) | Q(mobile_phone=query) | Q(email=query) | Q(stu_code=query) | Q(
                abstract__contains=query) | Q(res_form__psychologist__contains=query)).all().order_by(
            'uid')
    else:
        all_res = models.Reservation.objects.filter(res_form__status=1).all().order_by('uid')
    pages = request.GET.get('page')
    lists = Paginator(all_res, 10)
    try:
        res_list = lists.page(pages)
    except EmptyPage:
        res_list = lists.page(lists.num_pages)
    except PageNotAnInteger:
        res_list = lists.page(1)

    return render(request, 'reservation/reservation_receive_list.html', locals())


def get_status(uid):
    # 获取预约单现在的状态
    now_status = models.Res_Form_Data.objects.filter(res_form__uid=uid).last().status
    if now_status < 1:
        now_status = "等待预约"
    elif now_status == 1:
        now_status = "等待接待"
    elif now_status == 5:
        now_status = "等待受理"
    else:
        now_status = "完成"

    # 获取预约单填写的时间及填写人
    date = models.Reservation.objects.filter(uid=uid).first().create_datetime.strftime('%Y-%m-%d %H：%M')
    filler = models.Reservation.objects.filter(uid=uid).first().name
    # 初始化进度条数据
    status_data = f"等待受理:{filler}:{date}:网络或线下提交预约单, " + "预约受理:心理咨询中心:暂无:预约开始受理, 等待预约:{}:{}:预约成功, 等待接待:心理咨询中心:{}:等待预约者来访, 完成:{}:{}:完成接待工作"

    # 获取预约单所有的操作
    for i in [2, 4]:
        operate = models.Operation.objects.filter(ope_form__uid=uid, operation=i).all()
        name = ""
        date_time = ""
        if operate:
            for item in operate:
                name += item.operator.username + " "
                date_time = item.operate_datetime.strftime('%Y-%m-%d %H：%M')
        if i == 2:
            status_data = status_data.format(name, date_time, date_time, "{}", "{}")
        else:
            status_data = status_data.format(name, date_time)

    return status_data, now_status


def reservation_detail(request, uid):
    if request.method == 'GET':
        status_data, now_status = get_status(uid)
        obj = models.Reservation.objects.filter(uid=int(uid)).first()
        # 如果预约单状态为5（未验证预约），则只有主席助理以上可以查看
        if obj.res_form.first().status == 5 and request.STAFF.user.user_type < 5:
            return render(
                request,
                'error.html',
                {
                    'code': 403,
                    'msg': '此预约单为未验证的网络预约，请等待值班主席助理验证后再查看！'
                }
            )
        ope = models.Operation.objects.filter(ope_form__uid=int(uid)).all()
        invite_form = InviteModelForm()
        room_list_form = RoomListForm()
        return render(request, 'reservation/detail_reservation.html', locals())
    data = request.POST
    if data['method'] == 'reg':
        '''通过验证'''
        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()
        staff = data['staff1']
        if staff:
            # 判断是否有多个值班员
            staffs = staff.strip().split()
            existing_staffs, missing_staffs = models.UserInfo.check_users_active_by_names(staffs)
            if missing_staffs:
                error = {'staff1': '以下值班员不存在或已冻结：{}'.format(', '.join(missing_staffs))}
                return JsonResponse({'status': False, 'error': error})
            else:
                if request.STAFF.user.username in staffs:
                    error = {'staff1': '值班员与登录账户重复！'}
                    return JsonResponse({'status': False, 'error': error})
                else:
                    operations = []
                    for staff_member in existing_staffs:
                        staff_user = models.UserInfo.objects.get(username=staff_member,
                                                                 is_locked=False)  # 获取 UserInfo 实例
                        operations.append(models.Operation(
                            operator=staff_user,
                            ope_form=instance,
                            operation=9,
                        ))
                    models.Operation.objects.bulk_create(operations)  # 批量插入
        # staff = data['staff1']
        # if staff:
        #     exists = models.UserInfo.objects.filter(username=staff).exists()
        #     if exists:
        #         staff = models.UserInfo.objects.filter(username=staff).first()
        #         models.Operation.objects.create(
        #             operator=staff,
        #             ope_form=instance,
        #             operation=9,
        #         )
        #     else:
        #         errors = {'staff1': '该值班员不存在'}
        #         return JsonResponse({'status': False, 'error': errors})

        res_form_data.status = 0
        res_form_data.filler = request.STAFF.user
        res_form_data.save()

        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=9,
        )
        return JsonResponse({'status': True})

    elif data['method'] == 'work':
        '''添加工作记录'''
        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()
        staff = data['staff']
        operation = data['operation']
        if not operation:
            errors = {'operation': '请选择操作类型'}
            return JsonResponse({'status': False, 'error': errors})
        if staff:
            # 判断是否有多个值班员
            staffs = staff.strip().split()
            existing_staffs, missing_staffs = models.UserInfo.check_users_active_by_names(staffs)
            if missing_staffs:
                error = {'staff4': '以下值班员不存在或已冻结：{}'.format(', '.join(missing_staffs))}
                return JsonResponse({'status': False, 'error': error})
            else:
                if request.STAFF.user.username in staffs:
                    error = {'staff4': '值班员与登录账户重复！'}
                    return JsonResponse({'status': False, 'error': error})
                else:
                    operations = []
                    for staff_member in existing_staffs:
                        staff_user = models.UserInfo.objects.get(username=staff_member,
                                                                 is_locked=False)  # 获取 UserInfo 实例
                        operations.append(models.Operation(
                            operator=staff_user,
                            ope_form=instance,
                            operation=int(operation),
                        ))
                    models.Operation.objects.bulk_create(operations)  # 批量插入
        # if staff:
        #     exists = models.UserInfo.objects.filter(username=staff).exists()
        #     if exists:
        #         staff = models.UserInfo.objects.filter(username=staff).first()
        #         res_form_data.save()
        #         models.Operation.objects.create(
        #             operator=staff,
        #             ope_form=instance,
        #             operation=int(operation),
        #         )
        #     else:
        #         errors = {'staff4': '该值班员不存在'}
        #         return JsonResponse({'status': False, 'error': errors})
        else:
            errors = {'staff4': '请输入值班员姓名'}
            return JsonResponse({'status': False, 'error': errors})
        return JsonResponse({'status': True, 'msg': '工作记录已添加！'})

    elif data['method'] == 'add_comment':
        '''添加备注'''
        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()
        if res_form_data.comment:
            res_form_data.comment = res_form_data.comment + ' || ' + request.STAFF.user.username + ':' + data['comment']
        else:
            res_form_data.comment = request.STAFF.user.username + ':' + data['comment']
        res_form_data.save()
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=6,
        )
        return JsonResponse({'status': True})

    elif data['method'] == 'reservation':
        '''完成预约'''
        is_online = True if data.get("is_online") else False
        psychologist = data['name1']
        if psychologist.strip() == '':
            error = {'name1': '请填写咨询师姓名！'}
            return JsonResponse({'status': False, 'error': error})
        res_datetime = data['datetime'].strip()
        # 校验日期时间是否合法
        is_valid = validate_datetime_format(res_datetime)
        if not is_valid:
            error = {'datetime': '预约时间不合法！'}
            return JsonResponse({'status': False, 'error': error})

        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()

        # 校验其他值班员
        staff = data['staff']
        if staff:
            # 判断是否有多个值班员
            staffs = staff.strip().split()
            existing_staffs, missing_staffs = models.UserInfo.check_users_active_by_names(staffs)
            if missing_staffs:
                error = {'staff': '以下值班员不存在或已冻结：{}'.format(', '.join(missing_staffs))}
                return JsonResponse({'status': False, 'error': error})
            else:
                if request.STAFF.user.username in staffs:
                    error = {'staff': '值班员与登录账户重复！'}
                    return JsonResponse({'status': False, 'error': error})
                else:
                    # res_form_data.save()
                    operations = []
                    for staff_member in existing_staffs:
                        staff_user = models.UserInfo.objects.get(username=staff_member,
                                                                 is_locked=False)  # 获取 UserInfo 实例
                        operations.append(models.Operation(
                            operator=staff_user,
                            ope_form=instance,
                            operation=2,
                        ))
                    models.Operation.objects.bulk_create(operations)  # 批量插入

            # if exists:
            #     staff = models.UserInfo.objects.filter(username=staff).first()
            #     if staff == request.STAFF.user:
            #         errors = {'staff': '值班员与登录账户重复！'}
            #         return JsonResponse({'status': False, 'error': errors})
            #     else:
            #         res_form_data.save()
            #         models.Operation.objects.create(
            #             operator=staff,
            #             ope_form=instance,
            #             operation=2,
            #         )
            # else:
            #     errors = {'staff': '该值班员不存在'}
            #     return JsonResponse({'status': False, 'error': errors})

        # 如果是线上咨询
        if is_online:
            # 备注一下为线上预约：
            if res_form_data.comment:
                res_form_data.comment = res_form_data.comment + ' || ' + request.STAFF.user.username + "(自动备注):线上咨询"
            else:
                res_form_data.comment = request.STAFF.user.username + "(自动备注):线上咨询"
            res_form_data.save()
            models.Operation.objects.create(
                operator=request.STAFF.user,
                ope_form=instance,
                operation=6,
            )
        else:
            # 线下初次预约必须申请房间
            if data["room"].strip() == "":
                return JsonResponse(
                    {'status': False, 'error': {'room': '必填：线下咨询在初次预约时必须提交房间使用申请'}})
            # 构造一个新的QueryDict，在其中添加房间预约的数据
            room_query_dict = QueryDict('', mutable=True)
            room_data = {
                "room": data["room"],
                "start_time": res_datetime,
                "end_time": datetime.datetime.strptime(res_datetime, "%Y-%m-%d %H:%M") + datetime.timedelta(
                    hours=1),
                "applicant": psychologist,
                "reason": "【自动申请】{}号心理咨询".format(uid),
                "mobile_phone": request.STAFF.user.mobile_phone,
                "is_internal": True,
                "person_in_charge": request.STAFF.user.username,
                "operator": request.STAFF.user,
            }
            room_query_dict.update(room_data)
            # print(room_query_dict)
            form = RoomBookForm(data=room_query_dict)
            # 校验表单数据，校验房间申请是否存在冲突
            if not form.is_valid():
                return JsonResponse({"status": False, "error": form.errors})
            # 新增房间使用申请
            room_instance = models.Res_Room.objects.create(
                room=form.cleaned_data["room"],
                start_time=form.cleaned_data["start_time"],
                end_time=form.cleaned_data["end_time"],
                applicant=form.cleaned_data["applicant"],
                reason=form.cleaned_data["reason"],
                mobile_phone=form.cleaned_data["mobile_phone"],
                is_internal=form.cleaned_data["is_internal"],
                person_in_charge=form.cleaned_data["person_in_charge"],
                operator=request.STAFF.user
            )
            url = "{scheme}://{host}{path}".format(
                scheme=request.scheme,
                host=request.get_host(),
                path=reverse('room_check_list')
            )

            send_pusher_by_id(1, {
                "房间": room_instance.room,
                "申请人": room_instance.applicant,
                "申请原因": room_instance.reason,
                "值班员": request.STAFF.user.username,
                "审批链接": f'<a href="{url}">点击此处进行审批操作</a>'
            })

            res_form_data.room_res = room_instance  # 将房间申请与预约单关联

        res_form_data.processor = request.STAFF.user
        res_form_data.psychologist = data['name1']
        res_form_data.res_datetime = data['datetime']
        res_form_data.status = 1
        res_form_data.save()
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=2,
        )
        return JsonResponse({'status': True})

    elif data['method'] == 'change':
        '''改约'''
        is_online = True if data.get("is_online") == "on" else False  # 获取是否是线上咨询
        psychologist = data['name2']
        if psychologist.strip() == '':
            error = {'name2': '请填写咨询师姓名！'}
            return JsonResponse({'status': False, 'error': error})
        res_datetime = data['datetime2'].strip()
        # 校验日期时间是否合法
        is_valid = validate_datetime_format(res_datetime)
        if not is_valid:
            error = {'datetime2': '预约时间不合法！'}
            return JsonResponse({'status': False, 'error': error})

        # 获取当前的预约单和预约信息
        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()

        # 校验其他值班员
        staff = data['staff']
        if staff:
            # 判断是否有多个值班员
            staffs = staff.strip().split()
            existing_staffs, missing_staffs = models.UserInfo.check_users_active_by_names(staffs)
            if missing_staffs:
                error = {'staff2': '以下值班员不存在或已冻结：{}'.format(', '.join(missing_staffs))}
                return JsonResponse({'status': False, 'error': error})
            else:
                if request.STAFF.user.username in staffs:
                    error = {'staff2': '值班员与登录账户重复！'}
                    return JsonResponse({'status': False, 'error': error})
                else:
                    operations = []
                    for staff_member in existing_staffs:
                        staff_user = models.UserInfo.objects.get(username=staff_member,
                                                                 is_locked=False)  # 获取 UserInfo 实例
                        operations.append(models.Operation(
                            operator=staff_user,
                            ope_form=instance,
                            operation=3,
                        ))
                    models.Operation.objects.bulk_create(operations)  # 批量插入

        # staff = data['staff']
        # if staff:
        #     exists = models.UserInfo.objects.filter(username=staff).exists()
        #     if exists:
        #         staff = models.UserInfo.objects.filter(username=staff).first()
        #         if staff == request.STAFF.user:
        #             errors = {'staff2': '值班员与登录账户重复！'}
        #             return JsonResponse({'status': False, 'error': errors})
        #         else:
        #             res_form_data.save()
        #             models.Operation.objects.create(
        #                 operator=staff,
        #                 ope_form=instance,
        #                 operation=3,
        #             )
        #     else:
        #         errors = {'staff2': '该值班员不存在'}
        #         return JsonResponse({'status': False, 'error': errors})

        # 如果是线上咨询
        if is_online:
            # 如果以前有房间预约申请，则取消以前的申请
            if res_form_data.room_res:
                room_res = res_form_data.room_res
                # 取消以前的申请
                room_res.status = 3
                room_res.save()
            # 备注一下为线上预约：
            if res_form_data.comment:
                res_form_data.comment = res_form_data.comment + ' || ' + request.STAFF.user.username + "(自动备注):线上咨询"
            else:
                res_form_data.comment = request.STAFF.user.username + "(自动备注):线上咨询"
            res_form_data.save()
            models.Operation.objects.create(
                operator=request.STAFF.user,
                ope_form=instance,
                operation=6,
            )
        # 线下咨询重新申请房间的触发条件：
        # 1. 线下咨询且时间更改
        # 2. 线下咨询且房间更改
        # 3. 线下咨询且咨询师更改（因为房间申请关联了咨询师姓名）
        # 4. 线下咨询且当前无房间申请，或申请已被取消/拒绝
        is_room_res_needed = False
        if is_online is False:
            if res_form_data.res_datetime != data['datetime2']:
                is_room_res_needed = True
            elif res_form_data.psychologist != data['name2']:
                is_room_res_needed = True
            elif not res_form_data.room_res:
                is_room_res_needed = True
            elif res_form_data.room_res.status in [2, 3]:  # 2: 审核不通过, 3: 已取消
                is_room_res_needed = True
            elif str(res_form_data.room_res.room_id) != str(data.get("room")):
                is_room_res_needed = True

        if is_room_res_needed:
            if data["room"] == "":
                return JsonResponse({'status': False, 'error': {'room': '必填：线下预约必须申请房间'}})
            # 校验房间申请是否冲突
            # 构造一个新的QueryDict，在其中添加房间预约的数据
            room_query_dict = QueryDict('', mutable=True)
            room_data = {
                "room": data["room"],
                "start_time": res_datetime,
                "end_time": datetime.datetime.strptime(res_datetime, "%Y-%m-%d %H:%M") + datetime.timedelta(
                    hours=1),
                "applicant": psychologist,
                "reason": "【自动申请】{}号心理咨询".format(uid),
                "mobile_phone": request.STAFF.user.mobile_phone,
                "is_internal": True,
                "person_in_charge": request.STAFF.user.username,
                "operator": request.STAFF.user,
            }
            room_query_dict.update(room_data)
            # print(room_query_dict)
            form = RoomBookForm(data=room_query_dict)
            # 如果以前有房间预约申请，则取消以前的申请，没有以前的预约的话则直接进入房间申请数据校验
            if res_form_data.room_res:
                room_res = res_form_data.room_res
                # 保留以前申请的审批状态，备用
                old_status = res_form_data.room_res.status
                # 取消以前的申请
                room_res.status = 3
                room_res.save()
                # 校验本次申请的数据是否合法
                if not form.is_valid():
                    # 不合法的话需要将前面取消过的申请重新改回以前的审批状态
                    room_res.status = old_status
                    room_res.save()
                    return JsonResponse({"status": False, "error": form.errors})
            if not form.is_valid():
                return JsonResponse({"status": False, "error": form.errors})
            room_instance = models.Res_Room.objects.create(
                room=form.cleaned_data["room"],
                start_time=form.cleaned_data["start_time"],
                end_time=form.cleaned_data["end_time"],
                applicant=form.cleaned_data["applicant"],
                reason=form.cleaned_data["reason"],
                mobile_phone=form.cleaned_data["mobile_phone"],
                is_internal=form.cleaned_data["is_internal"],
                person_in_charge=form.cleaned_data["person_in_charge"],
                operator=request.STAFF.user
            )
            url = "{scheme}://{host}{path}".format(
                scheme=request.scheme,
                host=request.get_host(),
                path=reverse('room_check_list')
            )

            send_pusher_by_id(1, {
                "房间": room_instance.room,
                "申请人": room_instance.applicant,
                "申请原因": room_instance.reason,
                "值班员": request.STAFF.user.username,
                "审批链接": f'<a href="{url}">点击此处进行审批操作</a>'
            })

            res_form_data.room_res = room_instance  # 将房间申请替换为最新的房间申请

        res_form_data.processor = request.STAFF.user
        res_form_data.psychologist = data['name2']
        res_form_data.res_datetime = data['datetime2']
        res_form_data.status = 1
        res_form_data.save()
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=3,
        )
        return JsonResponse({'status': True})

    elif data['method'] == 'delete':
        '''废弃'''
        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()

        # 备注废弃原因
        if res_form_data.comment:
            res_form_data.comment = res_form_data.comment + ' || ' + request.STAFF.user.username + ':【废弃原因】' + data[
                'comment']
        else:
            res_form_data.comment = request.STAFF.user.username + ':【废弃原因】' + data['comment']
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=6,
        )

        # 如果有房间申请，则取消申请
        if res_form_data.room_res:
            room_res = res_form_data.room_res
            room_res.status = 3
            room_res.save()

        # 修改预约单状态为废弃状态
        res_form_data.status = 3
        res_form_data.save()
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=5,
        )

        return JsonResponse({'status': True, 'msg': '预约单已废弃！'})

    elif data['method'] == 'clear':
        '''清空'''
        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()

        # 如果有房间申请，则取消申请，并且取消与本预约单的关联
        if res_form_data.room_res:
            room_res = res_form_data.room_res
            room_res.status = 3
            room_res.save()
            res_form_data.room_res = None

        res_form_data.status = 0
        res_form_data.psychologist = None
        res_form_data.processor = None
        res_form_data.res_datetime = None
        res_form_data.save()
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=8,
        )
        return JsonResponse({'status': True, 'msg': '已清空预约详情，请值班员重新预约'})

    elif data['method'] == 'renewal':
        '''续约'''
        try:
            new_uid = models.Reservation.objects.last().uid + 1  # 读取最后一单的uid，并得出新预约单的uid
        except AttributeError:
            new_uid = 1
        # 1、获取原预约单的信息
        exists = models.Reservation.objects.filter(uid=uid).exists()
        if not exists:
            return JsonResponse({'status': False, 'error': '预约单不存在！'})
        old_instance = models.Reservation.objects.filter(uid=uid).first()
        fields_dict = {field: getattr(old_instance, field) for field in old_instance.__dict__.keys() if
                       field not in ['id', '_state', 'uid']}
        print(fields_dict)
        print(data)
        with transaction.atomic():
            # 2、根据旧预约单的信息直接拷贝生成新的预约单
            new_instance = models.Reservation.objects.create(
                **fields_dict,
                uid=new_uid,
            )
            # 3、生成新预约详情
            new_res_form_data = models.Res_Form_Data.objects.create(
                res_form=new_instance,
                filler=request.STAFF.user,
                processor=request.STAFF.user,
                comment=f"【第{uid}单续约】",
                status=1,
            )
            # 4、获取新提交的咨询师和预约时间
            new_psychologist = data['name3']
            new_res_datetime = data['datetime3']
            is_online = True if data.get("is_online") else False  # 获取是否是线上咨询

            # 5、校验新提交的咨询师和预约时间是否合法
            if new_psychologist.strip() == '':
                error = {'name3': '请填写咨询师姓名！'}
                transaction.set_rollback(True)  # 强制回滚当前事务
                return JsonResponse({'status': False, 'error': error})
            # 校验日期时间是否合法
            is_datetime_valid = validate_datetime_format(new_res_datetime)
            if not is_datetime_valid:
                error = {'datetime3': '预约时间不合法！'}
                transaction.set_rollback(True)  # 强制回滚当前事务
                return JsonResponse({'status': False, 'error': error})
            # 如果是线下咨询，并且预约时间更改了，则必须重新申请房间
            if data["room"] == "" and is_online is False:
                transaction.set_rollback(True)  # 强制回滚当前事务
                return JsonResponse({'status': False, 'error': {'room': '必填：线下预约必须申请房间'}})
            if not is_online:
                # 校验房间申请是否冲突
                # 构造一个新的QueryDict，在其中添加房间预约的数据
                room_query_dict = QueryDict('', mutable=True)
                room_data = {
                    "room": data["room"],
                    "start_time": new_res_datetime,
                    "end_time": datetime.datetime.strptime(new_res_datetime, "%Y-%m-%d %H:%M") + datetime.timedelta(
                        hours=1),
                    "applicant": new_psychologist,
                    "reason": "【自动申请】{}号心理咨询".format(new_uid),
                    "mobile_phone": request.STAFF.user.mobile_phone,
                    "is_internal": True,
                    "person_in_charge": request.STAFF.user.username,
                    "operator": request.STAFF.user,
                }
                # 用form校验房间申请是否冲突
                room_query_dict.update(room_data)
                room_form = RoomBookForm(data=room_query_dict)
                if not room_form.is_valid():
                    transaction.set_rollback(True)  # 强制回滚当前事务
                    return JsonResponse({"status": False, "error": room_form.errors})
                # 生成新的房间申请
                room_instance = models.Res_Room.objects.create(**room_form.cleaned_data, operator=request.STAFF.user)
                url = "{scheme}://{host}{path}".format(
                    scheme=request.scheme,
                    host=request.get_host(),
                    path=reverse('room_check_list')
                )
                send_pusher_by_id(1, {
                    "房间": room_instance.room,
                    "申请人": room_instance.applicant,
                    "申请原因": room_instance.reason,
                    "值班员": request.STAFF.user.username,
                    "审批链接": f'<a href="{url}">点击此处进行审批操作</a>'
                })
                new_res_form_data.room_res = room_instance  # 将房间申请替换为最新的房间申请

                # 6、记录操作记录
                new_res_form_data.processor = request.STAFF.user
                new_res_form_data.psychologist = new_psychologist
                new_res_form_data.res_datetime = new_res_datetime
                new_res_form_data.status = 1
                new_res_form_data.save()
                models.Operation.objects.create(
                    operator=request.STAFF.user,
                    ope_form=new_instance,
                    operation=10,
                )
                staff = data['staff']
                if staff:
                    # 判断是否有多个值班员
                    staffs = staff.strip().split()
                    existing_staffs, missing_staffs = models.UserInfo.check_users_active_by_names(staffs)
                    if missing_staffs:
                        error = {'staff5': '以下值班员不存在或已冻结：{}'.format(', '.join(missing_staffs))}
                        transaction.set_rollback(True)  # 强制回滚当前事务
                        return JsonResponse({'status': False, 'error': error})
                    else:
                        if request.STAFF.user.username in staffs:
                            error = {'staff5': '值班员与登录账户重复！'}
                            transaction.set_rollback(True)  # 强制回滚当前事务
                            return JsonResponse({'status': False, 'error': error})
                        else:
                            operations = []
                            for staff_member in existing_staffs:
                                staff_user = models.UserInfo.objects.get(username=staff_member,
                                                                         is_locked=False)  # 获取 UserInfo 实例
                                operations.append(models.Operation(
                                    operator=staff_user,
                                    ope_form=new_instance,
                                    operation=10,
                                ))
                            models.Operation.objects.bulk_create(operations)  # 批量插入

        return JsonResponse({'status': True, 'msg': '续约成功！', 'new_uid': new_uid})

    elif data['method'] == 'finish':
        '''接待完成'''
        instance = models.Reservation.objects.filter(uid=uid).first()
        res_form_data = models.Res_Form_Data.objects.filter(res_form__uid=uid).first()
        res_form_data.status = 2

        # 校验其他值班员
        staff = data['staff']
        if staff:
            # 判断是否有多个值班员
            staffs = staff.strip().split()
            existing_staffs, missing_staffs = models.UserInfo.check_users_active_by_names(staffs)
            if missing_staffs:
                error = {'staff3': '以下值班员不存在或已冻结：{}'.format(', '.join(missing_staffs))}
                return JsonResponse({'status': False, 'error': error})
            else:
                if request.STAFF.user.username in staffs:
                    error = {'staff3': '值班员与登录账户重复！'}
                    return JsonResponse({'status': False, 'error': error})
                else:
                    operations = []
                    for staff_member in existing_staffs:
                        staff_user = models.UserInfo.objects.get(username=staff_member,
                                                                 is_locked=False)  # 获取 UserInfo 实例
                        operations.append(models.Operation(
                            operator=staff_user,
                            ope_form=instance,
                            operation=4,
                        ))
                    models.Operation.objects.bulk_create(operations)  # 批量插入
        # staff = data['staff']
        # if staff:
        #     exists = models.UserInfo.objects.filter(username=staff).exists()
        #     if exists:
        #         staff = models.UserInfo.objects.filter(username=staff).first()
        #         if staff == request.STAFF.user:
        #             errors = {'staff3': '值班员与登录账户重复！'}
        #             return JsonResponse({'status': False, 'error': errors})
        #         else:
        #             res_form_data.save()
        #             models.Operation.objects.create(
        #                 operator=staff,
        #                 ope_form=instance,
        #                 operation=4,
        #             )
        #     else:
        #         errors = {'staff3': '该值班员不存在'}
        #         return JsonResponse({'status': False, 'error': errors})
        res_form_data.save()
        models.Operation.objects.create(
            operator=request.STAFF.user,
            ope_form=instance,
            operation=4,
        )

        if staff:
            return JsonResponse(
                {'status': True,
                 'msg': f'接待已完成,接待者：{request.STAFF.user.username}|{"|".join(staff.strip().split())}'})
        return JsonResponse({'status': True, 'msg': f'接待已完成,接待者：{request.STAFF.user.username}'})
    return render(request, 'reservation/detail_reservation.html', locals())


def calendar(request):
    # 获取本周所有的未接待预约
    # 1、获取当前周数与未接待预约的周数比较，并获取所有本周预约
    now_week = datetime.datetime.now().isocalendar()[1]
    res_all_list = models.Reservation.objects.filter(res_form__status=1).all()
    res_data = {1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: []}
    # 2、获取本周预约分别在周几，以及他的开始时间
    for item in res_all_list:
        date_str = item.res_form.first().res_datetime
        # print(date_str)
        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            return render(request, 'error.html',
                          {'code': 500, 'msg': f'日期格式错误，请检查第{item.uid}单咨询是否正确填写预约时间！'})
        if date_obj.isocalendar()[1] == now_week:
            res_data[date_obj.isoweekday()].append(
                [item.uid, item.res_form.first().psychologist, date_obj.isoweekday(), date_obj.hour, date_obj.time()])
    # print(res_data)
    monday_date = datetime.datetime.now().day - datetime.datetime.now().isoweekday() + 1
    return render(request, 'reservation/calendar.html', locals())


def consultation_calendar(request):
    """本周咨询预约周历（栅格式）。

    **与上面那个 calendar() 是两回事，不要合并**：
      - `calendar()`          —— 平台原有的「小时时间轴」版，路由 /calendar/，保留不动
      - `consultation_calendar()` —— 新增的**栅格**版，路由 /consultation/calendar/，
        视觉与冥想室周历一致（行按时段/小时、列按周一~周日、色块可点）

    行 = 小时（7:00-20:00，共 14 行），不是冥想室那种固定 11 档 ——
    咨询预约的时段是值班员自由填写到分钟的整点，没有固定档位。

    与冥想室周历的一处**有意改进**：咨询时间存在 `Res_Form_Data.res_datetime`
    这个字符串字段里，没法在 DB 层按日期区间过滤，只能在 Python 侧解析归周。
    原来那版遇到一条（status=1 的）格式坏的单会**整页替换成错误页**
    （HTTP 仍是 200，但周历完全看不到了，实测如此）；这里改为跳过坏数据继续渲染，
    并在页面顶部提示有几条被跳过，不让一条脏数据拖垮整个周历。
    """
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.isoweekday() - 1)
    sunday = monday + datetime.timedelta(days=6)

    # 只按状态收窄（0 预约未完成 / 1 接待未完成），与冥想室周历同口径
    res_all = models.Reservation.objects.filter(
        res_form__status__in=(0, 1)).select_related()

    # 按 (星期, 小时) 建索引；不返回整行对象，模板只做 for 循环
    bucket = {}
    skipped_bad_datetime = 0
    for item in res_all:
        form = item.res_form.first()
        if form is None or not form.res_datetime:
            continue
        try:
            date_obj = datetime.datetime.strptime(form.res_datetime, "%Y-%m-%d %H:%M")
        except ValueError:
            skipped_bad_datetime += 1
            continue
        if not (monday <= date_obj.date() <= sunday):
            continue
        bucket.setdefault((date_obj.isoweekday(), date_obj.hour), []).append({
            'uid': item.uid,
            'name': item.name,
            'psychologist': form.psychologist or '—',
            'hhmm': date_obj.strftime('%H:%M'),
            'status': form.status,
        })

    week_days = [
        (1, '周一', monday), (2, '周二', monday + datetime.timedelta(days=1)),
        (3, '周三', monday + datetime.timedelta(days=2)),
        (4, '周四', monday + datetime.timedelta(days=3)),
        (5, '周五', monday + datetime.timedelta(days=4)),
        (6, '周六', monday + datetime.timedelta(days=5)), (7, '周日', sunday),
    ]

    # 视图侧先把二维表铺平成"行列表"，模板只做 for 循环
    # （Django 1.11 模板不支持 dict[变量] 这种取值）
    calendar_rows = []
    for hour in range(7, 21):     # 7:00 - 20:00
        cells = []
        for wd, wname, wdate in week_days:
            cells.append({
                'date': wdate,
                'is_today': wdate == today,
                'events': bucket.get((wd, hour), []),
            })
        calendar_rows.append({
            'label': '{:02d}:00 - {:02d}:00'.format(hour, hour + 1),
            'cells': cells,
        })

    return render(request, 'reservation/consultation_calendar.html', locals())


def consultation_appointment(request):
    if request.method == "GET":
        return render(request, 'reservation/consultation_appointment.html')

    '''POST请求则验证表单'''
    try:
        uid = models.Reservation.objects.last().uid + 1  # 读取最后一单的uid，并得出新预约单的uid
    except AttributeError:
        uid = 1
    form = NewReservationInviteForm(data=request.POST)
    if form.is_valid():  # 判断表单是否有效
        instance = form.instance
        instance.uid = uid  # 为预约单添加单号
        instance = form.save()  # 保存预约单
        # 修改预约单状态
        models.Res_Form_Data.objects.create(
            res_form=instance,
            filler=request.STAFF.user,
            processor=None,
            comment=None,
            status=5,
        )
        return JsonResponse({'status': True})
    return JsonResponse({'status': False, 'error': form.errors})


def res_share_code(request, res_id):
    form = InviteModelForm(data=request.POST)
    if form.is_valid():
        """
        1. 创建随机的邀请码
        2. 验证码保存到数据库
        """
        res_obj = models.Reservation.objects.filter(id=res_id).first()
        random_invite_code = init_code(request.STAFF.user.mobile_phone)
        form.instance.consult = res_obj
        form.instance.code = random_invite_code
        form.instance.creator = request.STAFF.user
        form.save()

        # 将验邀请码返回给前端，前端页面上展示出来。
        url = "{scheme}://{host}{path}".format(
            scheme=request.scheme,
            host=request.get_host(),
            path=reverse('share_visit', kwargs={'code': random_invite_code})
        )

        return JsonResponse({'status': True, 'data': url})
    return JsonResponse({'status': False, 'error': form.errors})


def share_visit(request, code):
    current_datetime = datetime.datetime.now()

    invite_object = models.ResShare.objects.filter(code=code).first()
    if not invite_object:
        return render(request, 'error.html', {'code': 404, 'msg': '分享码不存在'})

    # 是否过期？
    limit_datetime = invite_object.create_datetime + datetime.timedelta(minutes=invite_object.period)
    if current_datetime > limit_datetime:
        return render(request, 'error.html', {'code': 404, 'msg': '预约详情分享已过期'})

    # 数量限制？
    if invite_object.count:
        if invite_object.use_count >= invite_object.count:
            return render(request, 'error.html', {'code': 404, 'msg': '访问次数已用尽！请联系心协值班员重新发送链接！'})
        invite_object.use_count += 1
        invite_object.save()

    obj = invite_object.consult
    use_count = invite_object.use_count
    rest_count = invite_object.count - use_count
    staff = invite_object.creator

    # 获取访问者ip、浏览器user-agent等信息作水印用
    if 'HTTP_X_FORWARDED_FOR' in request.META:
        ip = request.META.get('HTTP_X_FORWARDED_FOR')
    else:
        ip = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT')

    return render(request, 'reservation/share_reservation.html', locals())


def operate_history(request):
    return render(request, 'reservation/operate_history.html', locals())


def api_history(request):
    if request.method == "GET":
        count = request.GET.get('count')
        res = {}
        if count:
            count = int(count)
            if count >= 500:
                count = 500
            if count <= 1:
                count = 1
            try:
                ope_list = models.Operation.objects.order_by('-id').all()[:count]
                res['status'] = True
                res['data'] = [{'uid': i.ope_form.uid, 'time': i.operate_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                                'operator': i.operator.username,
                                'operation': i.operation} for i in ope_list]
                return JsonResponse(res)
            except BaseException:
                return JsonResponse({'status': False, 'error': 'there is no items'})

        try:
            today = datetime.datetime.now()
            ope_list = models.Operation.objects.filter(
                Q(operate_datetime__year=today.year) & Q(operate_datetime__month=today.month) & Q(
                    operate_datetime__day=today.day)).order_by('-id')
            res['status'] = True
            res['data'] = [{'uid': i.ope_form.uid, 'time': i.operate_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                            'operator': i.operator.username,
                            'operation': i.operation} for i in ope_list]
            return JsonResponse(res)
        except BaseException as e:
            return JsonResponse({'status': False, 'error': "服务器错误，请联系管理员！"})


def api_check_statistics(request):
    if request.method == "GET":
        today = datetime.datetime.today()
        res = {
            'status': True,
            'data': [
                {'name': "appointment-today", 'num': models.Operation.objects.filter(
                    Q(operation=2) & Q(operate_datetime__year=today.year) & Q(operate_datetime__month=today.month) & Q(
                        operate_datetime__day=today.day)).count()},
                {'name': "reception-today", 'num': models.Operation.objects.filter(
                    Q(operation=4) & Q(operate_datetime__year=today.year) & Q(operate_datetime__month=today.month) & Q(
                        operate_datetime__day=today.day)).count()},
                {'name': "re-appointment-today", 'num': models.Operation.objects.filter(
                    Q(operation=3) & Q(operate_datetime__year=today.year) & Q(operate_datetime__month=today.month) & Q(
                        operate_datetime__day=today.day)).count()},
                {'name': "cancel-today", 'num': models.Operation.objects.filter(
                    Q(operation=5) & Q(operate_datetime__year=today.year) & Q(operate_datetime__month=today.month) & Q(
                        operate_datetime__day=today.day)).count()},
            ]
        }
        return JsonResponse(res)
    return JsonResponse({'status': False, 'error': 'invalid request method!'})


def survey(request, res_id, code):
    exists = models.Res_Form_Data.objects.filter(res_form_id=res_id).exists()
    if not exists:
        return render(request, 'error.html', {'code': 404, 'msg': '咨询单不存在！'})
    res_obj = models.Res_Form_Data.objects.filter(res_form_id=res_id).first()
    if res_obj.is_survey_completed:
        return render(request, 'error.html', {'code': 401, 'msg': '该咨询的反馈已完成，感谢您的支持！'})
    if code != res_obj.survey_code:
        return render(request, 'error.html', {'code': 401, 'msg': '校验失败，无权限访问！'})

    if request.method == 'GET':
        return render(request, 'reservation/survey.html', locals())

    data: dict = dict(request.POST)
    print(data)
    # 数据清理检查
    data.pop('csrfmiddlewaretoken')
    form = ReservationSurveyForm(request.POST)
    if form.is_valid():
        data: str = json.dumps(data)
        res_obj.is_survey_completed = True
        res_obj.survey_data = data
        res_obj.save()
        print(data)
        return JsonResponse({'status': True, 'msg': '提交成功！'})
    return JsonResponse({'status': False, 'msg': '提交失败，请检查！', 'error': form.errors})


def send_survey(request, res_id):
    """
    1、生成校验码
    2、发送邮件
        1、发送邮件
        2、保存校验码、修改满意度调查相关的字段
    """
    if request.method != "GET":
        return JsonResponse({'status': False, 'msg': '不合法的请求方式！'})
    if request.STAFF.user.user_type < 4:
        return JsonResponse({'status': False, 'msg': '权限不足！'})
    res_obj = models.Res_Form_Data.objects.filter(res_form_id=res_id).first()
    # 1、判断预约单是否已经接待
    if res_obj.status != 2:
        return JsonResponse({'status': False, 'msg': '预约状态错误！'})
    # 2、判断否已经发送过调查邀请
    if res_obj.invited:
        return JsonResponse({'status': False, 'msg': '请勿重复发送调查邀请！'})
    # 3、生成校验码
    random_code: str = init_code("{}{}".format(res_obj.res_form_id, res_obj.res_datetime))
    url: str = "{scheme}://{host}{path}".format(
        scheme=request.scheme,
        host=request.get_host(),
        path=reverse('reservation_survey', kwargs={'res_id': res_obj.res_form_id, 'code': random_code})
    )
    psychologist: str = res_obj.psychologist
    res_datetime: str = res_obj.res_datetime
    content: str = '''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/><meta http-equiv="X-UA-Compatible"content="IE=edge"/><meta name="viewport"content="width=device-width, initial-scale=1.0"/><title>咨询调研</title><style>*{padding:0;margin:0;box-sizing:border-box}body{width:100%}a{text-decoration:none}.top{background-color:white;height:56px;width:100vw;border-top:solid 1px#ddd;border-left:solid 1px#ddd;border-right:solid 1px#ddd;display:flex;justify-content:center;align-items:center}.main{background-color:#eeeeee;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='99' height='99' viewBox='0 0 200 200'%3E%3Cpolygon fill='%23fafafa' fill-opacity='0.8' points='100 0 0 100 100 100 100 200 200 100 200 0'/%3E%3C/svg%3E");min-height:calc(100vh-56px);display:flex;flex-direction:column;justify-content:start;align-items:center}.box{margin-top:20px;width:90%;min-width:360px;text-align:center;background-color:white;box-shadow:0 0.125rem 0.25rem rgba(0,0,0,0.075);padding:20px;border-radius:20px}.btn{margin-top:10px;display:inline-block;font-weight:400;line-height:1.5;color:#212529;text-align:center;text-decoration:none;vertical-align:middle;cursor:pointer;-webkit-user-select:none;-moz-user-select:none;user-select:none;background-color:transparent;border:1px solid transparent;padding:0.375rem 0.75rem;font-size:1rem;border-radius:0.25rem;transition:color 0.15s ease-in-out,background-color 0.15s ease-in-out,border-color 0.15s ease-in-out,box-shadow 0.15s ease-in-out;color:#fff;background-color:#e17766;border-color:#e17766}.btn:hover{color:#fff;background-color:#a9594d;border-color:#a9594d}.content>p{font-size:16px;margin:10px}.signed{text-align:right;padding:10px;font-size:16px}.speech-info p{font-size:16px;color:#666}.speech{padding:5px 0}.footer{font-size:12px;text-align:center;color:#666;padding:20px 0}</style></head><body><div class="top"><div class="logo"><img src="https://example.com/static/img/favicon.ico"alt="logo"style="width: 50px"/></div></div><div class="main"><div class="box"><h1>心理咨询反馈调查</h1><div class="content"style="padding-top: 20px"><p style="text-align: left">亲爱的同学：</p><p style="text-align: left; text-indent: 2rem">你好！为了更好地提供心理咨询服务，我们诚挚地邀请你对本次心理咨询进行评价，咨询师不会直接看到本次评价的信息，请放心填写。</p><p style="text-align: start; text-indent: 2rem">祝你生活愉快！</p><div class="signed"><p>心理协会</p></div></div><hr style="margin: 20px 0;border: none;border-top: 5px dotted #ddd;"/><div class="speech-info"><h2 style="padding: 10px 0">点击下方按钮参与调查</h2><div class="speech"><p style="color: #666; font-weight: bold">咨询信息</p><p style="color: #666; font-size: 14px">咨询师：''' + psychologist + '''</p><p style="color: #666; font-size: 14px">咨询时间：''' + res_datetime + '''</p></div></div><a href="''' + url + '''"type="button"class="btn">点此参与</a></div><div class="footer"><p>心理咨询预约地址：请在环境变量 CONSULTATION_ADDRESS 中配置</p><p>心理咨询预约电话：请在环境变量 CONSULTATION_PHONE 中配置</p><p>微信公众号：请在环境变量 WECHAT_OFFICIAL_ACCOUNT 中配置</p></div></div></body></html>'''

    # 如需异步发送，可在此接入 Celery 任务
    res = send_email(res_obj.res_form.email, 'SMUPA心理咨询评价反馈邀请', content, 'html')
    if res["code"] == 0:
        res_obj.survey_code = random_code
        res_obj.invited = True
        res_obj.save()
        return JsonResponse({'status': True, 'msg': '发送成功！'})
    return JsonResponse({'status': False, 'msg': '发送失败！'})


def survey_data(request, key):
    if request.method == 'GET':
        survey_set = models.Res_Form_Data.objects.filter(is_survey_completed=True).all()
        data = {{'psychologist': item.psychologist, 'data': item.survey_data} for item in survey_set}
        res = {'code': 0, 'message': '', 'data': data}
        return JsonResponse(res)


def survey_api_output(request, key):
    import json
    if request.method == "GET":
        if not settings.SURVEY_API_KEY or key != settings.SURVEY_API_KEY:
            return JsonResponse({'code': 401, 'message': 'Error: wrong key!', 'data': []})
        reservation_set = models.Res_Form_Data.objects.filter(is_survey_completed=True).all()
        res_data = {'code': 200, 'message': 'success', 'data': []}
        for item in reservation_set:
            res_data['data'].append({
                "res_id": item.res_form.uid,
                "psychologist": item.psychologist,
                **json.loads(item.survey_data)
            })
        return JsonResponse(res_data)
    return JsonResponse({'code': 502, 'message': 'Error: refused!', 'data': []})


def print_reservation(request, uid):
    if request.method != "GET":
        return JsonResponse({'status': False, 'msg': '不合法的请求方式！'})
    res_obj = models.Reservation.objects.filter(uid=int(uid)).first()
    if not res_obj:
        return JsonResponse({'status': False, 'msg': '预约单不存在！'})
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render(request, 'reservation/res_print.html', locals())


@csrf_exempt
def reservation_wps(request):
    if request.method == "GET":
        return JsonResponse(status=405, data={'status': False, 'message': 'Method Not Allowed'})
    try:
        json_data = json.loads(request.body)
        # 校验表单id是否一致
        if not settings.FORM_ID or json_data.get('formId') != settings.FORM_ID:
            return JsonResponse({'status': False, 'message': '无推送权限！'})
        # 获取答案列表
        answers: List[dict] = json_data.get('answerContents')
        # 构建QueryDict以便将答案填入表单，并进行校验
        res_query_dict = QueryDict(mutable=True)
        # 新建字典收集“其他”选项对应的答案
        extra_answers = {}
        for answer in answers:
            # 找到verbose_name对应的字段名
            field_name = get_field_name_by_verbose_name(models.Reservation, answer.get('title'))
            if field_name:
                # 找到选择项对应的key，非选择则返回原值，不做改动
                value = get_choice_key_or_original_value(models.Reservation, field_name, answer.get('value'))
                extra_value = get_multi_choice_extra_value(field_name, answer.get('value'))
                # 收集“其他”选项对应的答案
                if extra_value is not None:
                    extra_answers[answer.get('title')] = extra_value
                # 多个选项使用setlist方法
                if isinstance(value, list):
                    res_query_dict.setlist(field_name, value)
                else:
                    res_query_dict[field_name] = value
        # 把“其他”选项对应的答案补充进情况简介
        if extra_answers:
            res_query_dict["abstract"] = "【(补充信息){}】{}".format(
                ";".join([f"{k}：{v}" for k, v in extra_answers.items()]),
                res_query_dict["abstract"])
        form = NewReservationInviteForm(data=res_query_dict)
        if form.is_valid():
            # 避免多次重复提交相同的预约单，查看正在处理的预约单中是否有相同手机号的预约单
            exists = models.Reservation.objects.filter(
                mobile_phone=form.cleaned_data.get('mobile_phone'),
                res_form__status__in=[0, 1, 4, 5]
            ).exists()
            if exists:
                # 发现重复预约单，发送推送通知
                reservation = models.Reservation.objects.filter(
                    mobile_phone=form.cleaned_data.get('mobile_phone'),
                    res_form__status__in=[0, 1, 4, 5]
                ).order_by('-id').first()  # 通过反向排序取第一个
                url = "{scheme}://{host}{path}".format(
                    scheme=request.scheme,
                    host=request.get_host(),
                    path=reverse('reservation_detail', kwargs={"uid": reservation.uid})
                )
                send_pusher_by_id(3, {
                    "内容": "监测到疑似重复的预约单",
                    "单号": reservation.uid,
                    "预约单": f'<a href="{url}">点击此处查看工作平台上疑似重复的预约单</a>',
                    "来源": "金山表单",
                    "操作提示": "查看金山表单查看详情，并与值班平台上的疑似预约单信息进行核对，如未重复，请手动输入新预约单"
                })
            else:
                # 保存表单数据，生成新的预约单
                try:
                    uid = models.Reservation.objects.last().uid + 1  # 读取最后一单的uid，并得出新预约单的uid
                except AttributeError:
                    uid = 1
                instance = form.instance
                instance.uid = uid  # 为预约单添加单号
                instance = form.save()  # 保存预约单
                # 修改预约单状态
                models.Res_Form_Data.objects.create(
                    res_form=instance,
                    processor=None,
                    comment=None,
                    status=5,
                )
                url = "{scheme}://{host}{path}".format(
                    scheme=request.scheme,
                    host=request.get_host(),
                    path=reverse('reservation_detail', kwargs={"uid": uid})
                )
                send_pusher_by_id(3, {"内容": "平台接收到来自网络的新预约单", "来源": "金山表单", "单号": uid,
                                      "验证链接": f'<a href="{url}">点击此处进行预约单验证检查</a>'})
        else:
            send_pusher_by_id(2, {"title": "金山表单数据校验失败", "from": "reservation_wps", "data": str(form.errors)})
            send_pusher_by_id(3, {
                "内容": "来自网络的表单校验失败",
                "来源": "金山表单",
                "操作提示": "查看金山表单获取最新数据，并登录平台手动输入预约单，同时告知系统管理员"
            })
    except Exception as e:
        send_pusher_by_id(2, {
            "title": "【异常】金山表单数据异常",
            "from": "reservation_wps",
            "error_message": str(e),
            "stack_trace": traceback.format_exc(),
            "request_url": request.build_absolute_uri(),
            "request_method": request.method,
            "request_params": request.GET.dict() if request.method == 'GET' else request.POST.dict()
        })
    return JsonResponse({'bind_code': settings.FORM_ID})
