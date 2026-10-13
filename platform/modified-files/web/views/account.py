import datetime
from io import BytesIO

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import HttpResponse, redirect, render
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.encoding import escape_uri_path
from django.conf import settings

from utils.SMTP import send_email as send_to_email
from utils.image_code import check_code
from web import models
from web.forms.accountForms import RegisterModelForm, LoginForm, EmailSendForm, FindPasswordForm, FindChangePassword, \
    RegisterCheckForm, AdviseForm, EmailFindPassword


# Create your views here.
def index(request):
    version = "v2.9.4"
    return render(request, 'index.html', locals())


def register(request):
    """ 注册 """
    if request.method == 'GET':
        form = RegisterModelForm()
        return render(request, 'account/register.html', {'form': form})

    form = RegisterModelForm(data=request.POST)
    if form.is_valid():
        # 验证通过，写入数据库（密码要是密文）
        # instance = form.save，在数据库中新增一条数据，并将新增的这条数据赋值给instance
        # 用户表中新建一条数据（注册）
        instance = form.save()

        # 新建一条成员审核数据
        models.UserCheck.objects.create(user=instance)
        return JsonResponse({'status': True, 'data': '/login/'})
    return JsonResponse({'status': False, 'error': form.errors})


def login(request):
    """ 用户名和密码登录 """
    # 如果已经登陆则直接跳转到dashboard
    if request.STAFF.user:
        return redirect('dashboard')

    if request.method == 'GET':
        # 尝试获取next参数
        next_url = request.GET.get("next", "/dashboard/")
        form = LoginForm(request)
        return render(request, 'account/login.html', {'form': form, 'next': next_url})

    form = LoginForm(request, data=request.POST)
    next_url = request.POST.get("next", "/dashboard/")
    if form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user = models.UserInfo.objects.filter(
            Q(email=username) | Q(mobile_phone=username) | Q(username=username)).first()
        if user:
            if user.is_locked:
                form.add_error('username', '该用户正在被审核或已被冻结，请联系部长')
                return JsonResponse({'status': False, 'error': form.errors})

        # user_object = models.UserInfo.objects.filter(username=username, password=password).first()
        #  (手机=username and pwd=pwd) or (邮箱=username and pwd=pwd)

        user_object = models.UserInfo.objects.filter(
            Q(email=username) | Q(mobile_phone=username) | Q(username=username)).filter(
            password=password).first()

        if user_object:
            # 登录成功为止

            # 判断是否已登陆
            # if user_object.session_key != request.session.session_key: # 如果当前的session_key和以前的key不一样了，则代表不是同一个浏览器的登陆操作
            #    now = datetime.datetime.now()
            #    old_session = Session.objects.filter(Q(expire_date__gt=now)|Q(session_key=user_object.session_key)).first()
            #    if old_session:
            #        old_session.delete()
            request.session['user_id'] = user_object.id
            request.session.set_expiry(60 * 60 * 2)
            # user_object.session_key = request.session.session_key
            if user_object.user_type < 7:
                if request.META.get('HTTP_X_FORWARDED_FOR'):
                    ip = request.META.get("HTTP_X_FORWARDED_FOR")
                else:
                    ip = request.META.get("REMOTE_ADDR")
                agent = request.environ.get("HTTP_USER_AGENT")

                models.LoginTime.objects.create(
                    user=user_object,
                    ip=ip,
                    agent=agent
                )

            '''记得改成dashboard'''
            return JsonResponse({'status': True, 'next_url': next_url})
        form.add_error('username', '用户名或密码错误')
    return JsonResponse({'status': False, 'error': form.errors})


def logout(request):
    request.session.flush()
    return redirect('login')


def send_email(request):
    form = EmailSendForm(request, data=request.GET)
    print(form)
    if form.is_valid():
        return JsonResponse({'status': True})
    return JsonResponse({'status': False, 'error': form.errors})


def image_code(request):
    """ 生成图片验证码 """
    image_object, code = check_code()

    request.session['image_code'] = code
    request.session.set_expiry(60)  # 主动修改session的过期时间为60s

    stream = BytesIO()
    image_object.save(stream, 'png')
    return HttpResponse(stream.getvalue())


def dashboard(request):
    if request.method == "GET":
        reservation_all_count = models.Reservation.objects.all().count()  # 总计预约
        not_appointment_count = models.Reservation.objects.filter(res_form__status=0).count()  # 预约未完成数
        not_received_count = models.Reservation.objects.filter(res_form__status=1).count()  # 接待未完成数
        you_have_finished = models.Reservation.objects.filter(ope_form__operator=request.STAFF.user)  # 用户累计处理
        you_have_finished = models.Reservation.objects.filter(ope_form__operator=request.STAFF.user).values(
            'id').distinct().count()  # 用户累计处理
        risk_res_count = models.Reservation.objects.filter(Q(Q1=1) | Q(Q2=1) | Q(Q3=1) | Q(Q4=1)).count()  # 危机单总数
        # 完成预约比例
        processing_progress = 100.0 if reservation_all_count == 0 else ('%.1f' % float(
            (reservation_all_count - not_appointment_count - not_received_count) * 100 / reservation_all_count))
        # 危机单比例
        risk_rate = 0 if reservation_all_count == 0 else ('%.1f' % float(
            risk_res_count * 100 / reservation_all_count))
        # 未预约比例
        not_appointment_rate = 0 if reservation_all_count == 0 else ('%.1f' % float(
            not_appointment_count * 100 / reservation_all_count))
        # 未接待比例
        not_received_rate = 0 if reservation_all_count == 0 else ('%.1f' % float(
            not_received_count * 100 / reservation_all_count))

        # ---------- 冥想室预约处理（与上面心理预约完全同口径）----------
        # ⚠️ 整段兜底：冥想室的表不存在（忘了 migrate）或查询异常时，这里置 0 继续渲染，
        #    **绝不能让首页 500** —— 首页是值班员处理咨询预约的入口，
        #    冥想室出问题不该把主业务一起拖下水。
        try:
            med_all_count = models.Med_Reservation.objects.all().count()
            med_not_appointment_count = models.Med_Reservation.objects.filter(res_form__status=0).count()
            med_not_received_count = models.Med_Reservation.objects.filter(res_form__status=1).count()
            med_you_have_finished = models.Med_Reservation.objects.filter(
                ope_form__operator=request.STAFF.user).values('id').distinct().count()
            med_processing_progress = 100.0 if med_all_count == 0 else ('%.1f' % float(
                (med_all_count - med_not_appointment_count - med_not_received_count) * 100 / med_all_count))
            med_not_appointment_rate = 0 if med_all_count == 0 else ('%.1f' % float(
                med_not_appointment_count * 100 / med_all_count))
            med_not_received_rate = 0 if med_all_count == 0 else ('%.1f' % float(
                med_not_received_count * 100 / med_all_count))
            # 今日已签到的冥想室预约（值班员最关心的实时数字）
            med_today_checkin = models.Med_Reservation.objects.filter(
                checkin_datetime__year=datetime.datetime.now().year,
                checkin_datetime__month=datetime.datetime.now().month,
                checkin_datetime__day=datetime.datetime.now().day,
            ).count()

        except Exception as _med_err:
            print('[meditation] 首页统计失败，已置 0 跳过：{}'.format(_med_err))
            med_all_count = 0
            med_not_appointment_count = 0
            med_not_received_count = 0
            med_you_have_finished = 0
            med_processing_progress = 0
            med_not_appointment_rate = 0
            med_not_received_rate = 0
            med_today_checkin = 0

        # 获取通知列表
        notify_list = models.Notification.objects.all()[:6]

        return render(request, 'dashboard.html', locals())
    return HttpResponse("无效的访问方式！")


def multiple_choice_output_format(string: str, choice_tuple: tuple):
    # 将原始选项字符串转化为列表
    choice_list = string.strip(",")

    fmt_list = []
    for i in choice_tuple:
        if i[1] in choice_list:
            fmt_list.append((i[0], 1))
        else:
            fmt_list.append((i[0], 0))
    return fmt_list


def export_excel(request, obj):
    import xlwt
    from web import models
    from django.http import HttpResponse
    from io import BytesIO

    ws = xlwt.Workbook(encoding='utf-8')
    if obj == 'all_member':
        '''输出所有成员'''
        file_name = "心协成员表"
        list_obj = models.UserInfo.objects.all()
        w = ws.add_sheet('成员表')
        w.write(0, 0, u'成员姓名')
        w.write(0, 1, u'部门')
        w.write(0, 2, u'职务')
        w.write(0, 3, u'学号/工号')
        w.write(0, 4, u'学院')
        w.write(0, 5, u'专业班级')
        w.write(0, 6, u'邮箱')
        w.write(0, 7, u'手机号')
        excel_row = 1
        for item in list_obj:
            w.write(excel_row, 0, item.username)
            w.write(excel_row, 1, item.get_apartment_display())
            w.write(excel_row, 2, item.get_user_type_display())
            w.write(excel_row, 3, item.stu_code)
            w.write(excel_row, 4, item.get_college_display())
            w.write(excel_row, 5, item.class_name)
            w.write(excel_row, 6, item.email)
            w.write(excel_row, 7, item.mobile_phone)
            excel_row += 1

    elif obj == 'apartment_member':
        '''输出部门成员'''
        file_name = "心协部门成员表"
        list_obj = models.UserInfo.objects.filter(apartment=request.STAFF.user.apartment).all()
        w = ws.add_sheet('Sheet1')
        w.write(0, 0, u'成员姓名')
        w.write(0, 1, u'部门')
        w.write(0, 2, u'职务')
        w.write(0, 3, u'学号/工号')
        w.write(0, 4, u'学院')
        w.write(0, 5, u'专业班级')
        w.write(0, 6, u'邮箱')
        w.write(0, 7, u'手机号')
        excel_row = 1
        for item in list_obj:
            w.write(excel_row, 0, item.username)
            w.write(excel_row, 1, item.get_apartment_display())
            w.write(excel_row, 2, item.get_user_type_display())
            w.write(excel_row, 3, item.stu_code)
            w.write(excel_row, 4, item.get_college_display())
            w.write(excel_row, 5, item.class_name)
            w.write(excel_row, 6, item.email)
            w.write(excel_row, 7, item.mobile_phone)
            excel_row += 1

    elif obj == 'all_consultations':
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

        file_name = "心协预约信息汇总"
        list_obj = models.Reservation.objects.all()
        w = ws.add_sheet('预约信息汇总表')
        w.write(0, 0, u'编号')
        w.write(0, 1, u'创建时间')
        w.write(0, 2, u'状态')
        w.write(0, 3, u'最后操作时间')
        # 来访者信息
        w.write(0, 4, u'来访者姓名')
        w.write(0, 5, u'性别')
        w.write(0, 6, u'学院')
        w.write(0, 7, u'年级')
        w.write(0, 8, u'学号/工号')
        w.write(0, 9, u'手机号')
        w.write(0, 10, u'邮箱')
        # 来访问题
        col = 11
        for i in renji_choice:
            w.write(0, col, u'{}-{}'.format('人际交往', i[1]))
            col += 1

        for i in qinggan_choice:
            w.write(0, col, u'{}-{}'.format('情感问题', i[1]))
            col += 1

        for i in xueye_choice:
            w.write(0, col, u'{}-{}'.format('学业问题', i[1]))
            col += 1

        for i in zhiye_choice:
            w.write(0, col, u'{}-{}'.format('职业生涯', i[1]))
            col += 1

        for i in qingxu_choice:
            w.write(0, col, u'{}-{}'.format('情绪问题', i[1]))
            col += 1

        for i in xingxin_choice:
            w.write(0, col, u'{}-{}'.format('性心理', i[1]))
            col += 1

        # 危机评估
        w.write(0, col, u'情况简介')
        col += 1
        w.write(0, col, u'是否有伤害自己或者他人的想法')
        col += 1
        w.write(0, col, u'是否有伤害自己或者他人的行为')
        col += 1
        w.write(0, col, u'是什么行为')
        col += 1
        w.write(0, col, u'有被别人伤害的可能吗')
        col += 1
        w.write(0, col, u'是否服用精神类药物或喝酒')
        col += 1
        # 其他信息
        w.write(0, col, u'您从哪里了解心理咨询')
        col += 1
        w.write(0, col, u'谁推荐你来做心理咨询')
        col += 1
        w.write(0, col, u'是否同意作为教学资料')
        col += 1
        # 预约信息
        w.write(0, col, u'咨询师姓名')
        col += 1
        w.write(0, col, u'预定咨询时间')

        excel_row = 1
        for item in list_obj:
            w.write(excel_row, 0, item.uid)
            w.write(excel_row, 1, item.create_datetime.strftime("%Y/%m/%d %H:%M:%S"))
            w.write(excel_row, 2, item.res_form.first().get_status_display())
            w.write(excel_row, 3, item.res_form.first().operate_datetime.strftime("%Y/%m/%d %H:%M:%S"))
            w.write(excel_row, 4, item.name)
            w.write(excel_row, 5, item.get_sex_display())
            w.write(excel_row, 6, item.get_college_display())
            w.write(excel_row, 7, item.get_grade_display())
            w.write(excel_row, 8, item.stu_code)
            w.write(excel_row, 9, item.mobile_phone)
            w.write(excel_row, 10, item.email)

            col = 11
            answer_list = multiple_choice_output_format(item.get_renji_display(), renji_choice)
            for i in answer_list:
                w.write(excel_row, col, i[1])
                col += 1

            answer_list = multiple_choice_output_format(item.get_qinggan_display(), qinggan_choice)
            for i in answer_list:
                w.write(excel_row, col, i[1])
                col += 1

            answer_list = multiple_choice_output_format(item.get_xueye_display(), xueye_choice)
            for i in answer_list:
                w.write(excel_row, col, i[1])
                col += 1

            answer_list = multiple_choice_output_format(item.get_zhiye_display(), zhiye_choice)
            for i in answer_list:
                w.write(excel_row, col, i[1])
                col += 1

            answer_list = multiple_choice_output_format(item.get_qingxu_display(), qingxu_choice)
            for i in answer_list:
                w.write(excel_row, col, i[1])
                col += 1

            answer_list = multiple_choice_output_format(item.get_xingxin_display(), xingxin_choice)
            for i in answer_list:
                w.write(excel_row, col, i[1])
                col += 1

            # 危机评估
            w.write(excel_row, col, item.abstract)
            col += 1
            w.write(excel_row, col, item.get_Q1_display())
            col += 1
            w.write(excel_row, col, item.get_Q2_display())
            col += 1
            w.write(excel_row, col, item.Q2_1)
            col += 1
            w.write(excel_row, col, item.get_Q3_display())
            col += 1
            # 其他信息
            w.write(excel_row, col, item.get_Q4_display())
            col += 1
            w.write(excel_row, col, item.get_where_to_find_display())
            col += 1
            w.write(excel_row, col, item.get_who_tell_you_display())
            col += 1
            # 预约信息
            w.write(excel_row, col, item.get_agree_display())
            col += 1
            w.write(excel_row, col, item.res_form.first().psychologist)
            col += 1
            w.write(excel_row, col, item.res_form.first().res_datetime)
            excel_row += 1

    # sio = BytesIO()
    # sio.seek(0)
    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = F"attachment;filename*=utf-8''{escape_uri_path(file_name)}.xls"
    # response.write(sio.getvalue())

    ws.save(response)
    return response


'''
{
                // 提供一份数据。
                source: [
                    ["product", "总咨询人数", "系列二", "系列三"],
                    ["商船院", 19, 85.8, 93.7],
                    ["法学院", 16, 73.4, 55.1],
                    ["海科院", 10, 65.2, 82.5],
                    ["交运院", 29, 53.9, 39.1],
                    ["经管院", 39, 53.9, 39.1],
                    ["外院", 21, 53.9, 39.1],
                    ["文理院", 12, 53.9, 39.1],
                    ["物工院", 34, 53.9, 39.1],
                    ["信工院", 27, 53.9, 39.1],
                    ["其他", 25, 53.9, 39.1],
                ],
            },
            '''


def init_data_visible(request):
    dataset = {
        'source': [
            ["product", "总咨询人数", "女生", "男生"],
        ],
    }
    college_choice = (
        (0, '商船'),
        (1, '交运'),
        (2, '经管'),
        (3, '物工'),
        (4, '信工'),
        (5, '外语'),
        (6, '文理'),
        (7, '法'),
        (8, '海科'),
        (9, '物科'),
        (11, '马克思'),
        (12, '徐悲鸿'),
        (10, '其他'),
    )

    for item in college_choice:  # 分别查询每个学院的数据
        total = models.Reservation.objects.filter(
            ~Q(res_form__status=3) & ~Q(res_form__status=5) & Q(college=item[0])).count()
        girl = models.Reservation.objects.filter(
            ~Q(res_form__status=3) & ~Q(res_form__status=5) & Q(college=item[0], sex=0)).count()
        boy = models.Reservation.objects.filter(
            ~Q(res_form__status=3) & ~Q(res_form__status=5) & Q(college=item[0], sex=1)).count()
        if item[0] == 10:  # 当key为"其他"时，则不添加"学院两个字"
            data = [f"{item[1]}", total, girl, boy]
        else:
            data = [f"{item[1]}学院", total, girl, boy]
        dataset['source'].append(data)
    return JsonResponse(
        {'status': True, 'dataset': dataset, 'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


def find_password(request):
    if request.method == "GET":
        '''GET请求则返回页面'''
        form = FindPasswordForm(request)
        return render(request, 'account/find_password.html', locals())
    form = FindPasswordForm(request, data=request.POST)
    if form.is_valid():
        '''若验证成功则直接登录进入修改密码的界面'''
        email = form.cleaned_data['email']
        user_object = models.UserInfo.objects.filter(email=email).filter().first()
        if user_object:
            # 登录成功为止
            request.session['user_id'] = user_object.id
            request.session.set_expiry(60 * 60 * 2)
            if user_object.user_type < 7:
                if request.META.get('HTTP_X_FORWARDED_FOR'):
                    ip = request.META.get("HTTP_X_FORWARDED_FOR")
                else:
                    ip = request.META.get("REMOTE_ADDR")
                agent = request.environ.get("HTTP_USER_AGENT")

                models.LoginTime.objects.create(
                    user=user_object,
                    ip=ip,
                    agent=agent
                )

            return redirect('find_change_password', user_id=user_object.id)
    return render(request, 'account/find_password.html', {'form': form})


def find_change_password(request, user_id):
    if request.method == "GET":
        form = FindChangePassword(request)
        return render(request, 'account/find_change_password.html', locals())
    form = FindChangePassword(request, data=request.POST)
    if form.is_valid():
        password = form.cleaned_data['newpassword']
        user_object = models.UserInfo.objects.filter(id=request.STAFF.user.id).first()
        user_object.password = password
        user_object.save()
        return JsonResponse({'status': True, 'data': '/index/'})

    return JsonResponse({'status': False, 'error': form.errors})


def send_email_find(request):
    form = EmailFindPassword(request, data=request.GET)
    if form.is_valid():
        return JsonResponse({'status': True})

    return JsonResponse({'status': False, 'error': form.errors})


def check_newmember(request, request_id):
    """
    审核新成员
    :param request:
    :return:
    """
    # 1、判断是否有资格获取信息
    if request.STAFF.user.user_type < 2:
        msg = '此账号无审核权限！'
        return render(request, 'error.html', {'msg': msg})
    if request.method == 'GET':
        # 2、获取注册申请
        request_id = int(request_id)
        if request_id != 0:
            request_object = models.UserCheck.objects.filter(user_id=request_id).first().user
            username = request_object.username
            form = RegisterCheckForm(instance=request_object)
        else:
            request_object = None
        '''仅主席团能看到所有申请注册的人，部长只能看本部成员'''
        if request.STAFF.user.user_type >= 5:
            check_list = models.UserCheck.objects.filter(is_read=False).all()
        else:
            apartment = request.STAFF.user.apartment  # 获取当前账号的部门
            check_list = models.UserCheck.objects.filter(is_read=False, user__apartment=apartment)  # 只获取当前部门的成员
        return render(request, 'account/check_member_list.html', locals())

    '''POST请求'''
    # 3、完成审核操作

    try:
        request_method = request.POST['method']
        '''如果是拒绝用户申请'''
        print(request.POST)
        check = models.UserCheck.objects.filter(user_id=request.POST['id']).first()
        check.is_read = True
        check.save()
        return JsonResponse({'status': True})
    except MultiValueDictKeyError:
        form = RegisterCheckForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            apartment = form.cleaned_data['apartment']
            user_type = form.cleaned_data['user_type']
            user = models.UserInfo.objects.filter(username=username).last()
            user.username = username
            user.apartment = apartment
            user.user_type = user_type
            user.is_locked = False
            user.save()
            check = models.UserCheck.objects.filter(user_id=request_id).first()
            check.is_read = True
            check.save()
            return redirect('check_newmember', request_id=0)
        return redirect('check_newmember', request_id=0)


def all_member(request):
    # 进行权限验证
    if request.STAFF.user.user_type < 2:
        return render(request, "error.html", {'msg': '操作权限不足！', 'code': 403})
    all_res = models.UserInfo.objects.filter(apartment=request.STAFF.user.apartment, user_type__gt=0).order_by(
        '-user_type').all()
    pages = request.GET.get('page')
    lists = Paginator(all_res, 10)
    try:
        member_list = lists.page(pages)
    except EmptyPage:
        member_list = lists.page(lists.num_pages)
    except PageNotAnInteger:
        member_list = lists.page(1)
    return render(request, 'account/all_member.html', locals())


def all_all_member(request):
    # 进行权限验证
    if request.STAFF.user.user_type < 4:
        return render(request, "error.html", {'msg': '操作权限不足！', 'code': 403})
    all_res = models.UserInfo.objects.filter(user_type__gt=0).all().order_by('-user_type' and '-apartment')
    pages = request.GET.get('page')
    lists = Paginator(all_res, 15)
    try:
        member_list = lists.page(pages)
    except EmptyPage:
        member_list = lists.page(lists.num_pages)
    except PageNotAnInteger:
        member_list = lists.page(1)

    return render(request, 'account/all_all_member.html', locals())


def edit_member(request):
    if request == 'GET':
        return

    data = request.POST
    if data['method'] == 'delete':
        obj = models.UserInfo.objects.filter(id=int(data['id'])).first()
        obj.user_type = 0
        obj.save()
        return JsonResponse({'status': True, 'msg': f'已成功删除{obj.username}'})
    obj = models.UserInfo.objects.filter(id=int(data['id'])).first()
    if data['username']:
        obj.username = data['username']
    if data['apartment']:
        obj.apartment = data['apartment']
    if data['user_type']:
        obj.user_type = data['user_type']
    if data['stu_code']:
        obj.stu_code = data['stu_code']
    if data['college']:
        obj.college = data['college']
    if data['class_name']:
        obj.class_name = data['class_name']
    if data['mobile_phone']:
        obj.mobile_phone = data['mobile_phone']
    if 'email' in data and request.STAFF.user.user_type > 6:
        obj.email = data['email']
    obj.save()
    return JsonResponse({'status': True})


def login_monitor(request):
    if request.STAFF.user.user_type < 4:
        code = 404
        msg = '用户权限不足！'
        return render(request, 'error.html', locals())
    all_res = models.LoginTime.objects.filter(user__user_type__gt=0).all().order_by("-id")
    pages = request.GET.get('page')
    lists = Paginator(all_res, 30)
    try:
        data = lists.page(pages)
    except EmptyPage:
        data = lists.page(lists.num_pages)
    except PageNotAnInteger:
        data = lists.page(1)
    return render(request, 'account/login_monitor.html', locals())


def edit_userinfo(request):
    if request == 'GET':
        '''get请求不允许直接返回'''
        return

    data = request.POST
    obj = models.UserInfo.objects.filter(id=request.STAFF.user.id).first()
    if data['username']:
        obj.username = data['username']
    if data['stu_code']:
        obj.stu_code = data['stu_code']
    if data['class_name']:
        obj.class_name = data['class_name']
    if data['mobile_phone']:
        obj.mobile_phone = data['mobile_phone']
    if data['college']:
        obj.college = data['college']
    obj.save()
    return JsonResponse({'status': True})


def delete_all(request):
    '''
    把所有除指导老师外的成员改为往届成员
    '''
    # 进行权限验证
    if request.STAFF.user.user_type < 7:
        return render(request, "error.html", {'msg': '操作权限不足！', 'code': 403})
    if request.method == "GET":
        user_list = models.UserInfo.objects.filter(user_type__lt=7).all()
        for user in user_list:
            user.user_type = 0
            user.save()
        return JsonResponse({'status': True})
    return HttpResponse("不支持的访问方式！")


def advise_to_email(request):
    if request.method == "GET":
        return HttpResponse("不支持的访问方式！")
    data = request.POST
    form = AdviseForm(data=data)
    if not form.is_valid():
        print("\n".join([f'{item[0]}:{item[1][0]}' for item in list(form.errors.items())]))
        error_msg = "\n".join([f'{item[0]}:{item[1][0]}' for item in list(form.errors.items())])
        return JsonResponse({'status': False, 'error': error_msg})
    email = form.cleaned_data.get("email")
    advise_content = form.cleaned_data.get("advise_content")
    email_content = "邮箱：{}\n建议内容：{}".format(email, advise_content)
    res = send_to_email(settings.FEEDBACK_EMAIL, "{}意见反馈".format(settings.SITE_NAME), email_content)
    if res.get("code") != 0:
        return JsonResponse({'status': False, 'error': '邮件发送失败！'})
    return JsonResponse({'status': True})
