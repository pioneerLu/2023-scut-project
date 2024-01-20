from rest_framework.decorators import api_view
from .Action import Action
from .models import *
from .serializers import *
from django.shortcuts import render


@api_view(['GET',"POST"])
# 管理员登录
def adminLogin(request):
  # 获取参数
  name = request.POST.get('name')
  password = request.POST.get('password')
  # 根据name查询
  user = admin.objects.filter(name=name).first()
  if not user:
    # 用户不存在,则直接返回错误消息
    return Action.fail("用户不存在")
  if user.password != password:
    # 用户存在,密码不一致,则直接返回错误消息
    return Action.fail("密码错误")
  # 登陆成功
  return Action.success(AdminSerializer(user, many = False).data)