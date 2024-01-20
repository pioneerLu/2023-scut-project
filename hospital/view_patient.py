from rest_framework.decorators import api_view
from .Action import Action
from .models import *
from .serializers import *

@api_view(['GET',"POST"])
# 患者注册
def patientRegister(request):
  # 获取参数
  name = request.POST.get('name')
  id_card = request.POST.get('id_card')
  phone = request.POST.get('phone')
  password = request.POST.get('password')
  sex = request.POST.get('sex')
  age = request.POST.get('age')
  # 查询身份证号是否已被注册
  sameIdCardUserList = user_patient.objects.filter(id_card=id_card)
  if sameIdCardUserList.exists() == True :
    # 如果已经被注册,则直接返回错误消息，并提示直接登录
    return Action.fail("您已注册,请直接登录")
  # 若没注册，添加入数据库
  user = user_patient(name=name, id_card=id_card, phone=phone, password=password, sex=sex, age=age)
  user.save()
  return Action.success()

@api_view(['GET',"POST"])
# 患者登录
def patientLogin(request):
  # 获取参数
  id_card = request.POST.get('name')
  password = request.POST.get('password')
  # 根据身份证号查询
  user = user_patient.objects.filter(id_card=id_card).first()
  if not user:
    # 用户不存在,则直接返回错误消息
    return Action.fail("用户不存在")
  if user.password != password:
    # 用户存在,密码不一致,则直接返回错误消息
    return Action.fail("密码错误")
  # 登陆成功
  return Action.success(UserPatientSerializer(user, many = False).data)

@api_view(['GET',"POST"])
# 患者列表
def patientList(request):
  return Action.success(UserPatientSerializer(user_patient.objects.all(), many = True).data)