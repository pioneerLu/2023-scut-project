from rest_framework.decorators import api_view
from .Action import Action
from .models import *
from .serializers import *
from django.shortcuts import render

@api_view(['GET',"POST"])
# 药品列表
def medicineList(request):
  list = medicine.objects.all()
  return Action.success(MedicineSerializer(list, many = True).data)

@api_view(['GET',"POST"])
# 药品列表
def medicineStrList(request):
  medicine_list = request.POST.get('medicine_list')
  medicine_list_arr = medicine_list.split(',')
  arr = []
  for de in medicine_list_arr:
    med = medicine.objects.filter(id=de).first()
    temp = {}
    temp['id'] = med.id
    temp['name'] = med.name
    temp['price'] = med.price
    temp['unit'] = med.unit
    arr.append(temp)
  return Action.success(arr)

@api_view(['GET',"POST"])
# 添加药品
def medicineAdd(request):
  # 获取参数
  name = request.POST.get('name')
  price = request.POST.get('price')
  unit = request.POST.get('unit')
  # 查询
  sameIdCardUserList = medicine.objects.filter(name=name)
  if sameIdCardUserList.exists() == True :
    # 如果已经被注册,则直接返回错误消息
    return Action.fail("已存在")
  # 若没注册，添加入数据库
  new_medicine = medicine(name=name, price=price, unit=unit)
  new_medicine.save()
  # 添加成功
  return Action.success()