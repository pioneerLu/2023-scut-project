from rest_framework.decorators import api_view
from .Action import Action
from .models import *
from .serializers import *
from django.shortcuts import render


@api_view(['GET',"POST"])
# 获取部门列表
def departmentList(request):
  # 获取参数
  # name = request.POST.get('name')
  # 根据name查询
  # user = department.objects.filter(name=name).first()
  list = department.objects.all()
  for item in list:
    item.doctor_num = user_doctor.objects.filter(department_id=item.id).count()
  # 登陆成功
  return Action.success(DepartmentSerializer(list, many = True).data)
  # return Action.success(list)