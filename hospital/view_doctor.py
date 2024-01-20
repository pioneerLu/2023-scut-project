from rest_framework.decorators import api_view
from .Action import Action
from .models import *
from .serializers import *
from django.shortcuts import render


@api_view(['GET',"POST"])
# 医生登录
def doctorLogin(request):
  # 获取参数
  id_card = request.POST.get('name')
  password = request.POST.get('password')
  # 根据身份证查询
  user = user_doctor.objects.filter(id_card=id_card).first()
  if not user:
    # 用户不存在,则直接返回错误消息
    return Action.fail("用户不存在")
  if user.password != password:
    # 用户存在,密码不一致,则直接返回错误消息
    return Action.fail("密码错误")
  # 登陆成功
  # return render(request, 'admin.html')
  return Action.success(UserDoctorSerializer(user, many = False).data)

@api_view(['GET',"POST"])
# 医生列表
def doctorList(request):
  list = user_doctor.objects.all()
  arr = []
  for item in list:
    temp = {}
    temp['id'] = item.id
    temp['name'] = item.name
    temp['id_card'] = item.id_card
    temp['department_id'] = item.department_id
    temp['department_name'] = department.objects.filter(id=item.department_id).first().name
    # temp['password'] = item.password
    # temp['status'] = item.status
    arr.append(temp)
  # 登陆成功
  return Action.success(arr)

@api_view(['GET',"POST"])
# 添加医生
def doctorAdd(request):
  # 获取参数
  name = request.POST.get('name')
  id_card = request.POST.get('id_card')
  department_id = request.POST.get('department_id')
  password = request.POST.get('password')
  # 查询身份证号是否已被注册
  sameIdCardUserList = user_doctor.objects.filter(id_card=id_card)
  if sameIdCardUserList.exists() == True :
    # 如果已经被注册,则直接返回错误消息
    return Action.fail("身份重复")
  # 若没注册，添加入数据库
  doctor = user_doctor(name=name, id_card=id_card, department_id=department_id, password=password)
  doctor.save()
  # 添加成功
  return Action.success()