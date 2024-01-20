from rest_framework.decorators import api_view
from .Action import Action
from .models import *
from .serializers import *
from django.shortcuts import render

@api_view(['GET',"POST"])
# 挂号列表
def orderList(request):
  user_id = request.POST.get('user_id')
  department_id = request.POST.get('department_id')
  doctor_id = request.POST.get('doctor_id')
  status = request.POST.get('status')
  list = order.objects.all()
  if user_id:
    list = list.filter(patient_id=user_id)
  if department_id:
    list = list.filter(department_id=department_id)
  if doctor_id:
    list = list.filter(doctor_id=doctor_id)
  if status:
    list = list.filter(status=status)
  arr = []
  print('list:', list)
  for item in list:
    temp = {}
    temp['id'] = item.id
    temp['patient_id'] = item.patient_id
    temp['patient_name'] = user_patient.objects.filter(id=item.patient_id).first().name 
    temp['department_id'] = item.department_id
    temp['department_name'] = department.objects.filter(id=item.department_id).first().name 
    temp['readme'] = item.readme
    temp['registration_fee'] = item.registration_fee
    temp['doctor_id'] = item.doctor_id
    temp['medicine_list'] = item.medicine_list
    checkDoctor = user_doctor.objects.filter(id=item.doctor_id).first()
    if checkDoctor:
      temp['doctor_name'] = checkDoctor.name
    else:
      temp['doctor_name'] = ''
    temp['order_advice'] = item.order_advice
    temp['total_cost'] = item.total_cost
    temp['status'] = item.status
    temp['time'] = item.time
    arr.append(temp)
  return Action.success(arr)

@api_view(['GET',"POST"])
# 添加就诊
def orderAdd(request):
  # 获取参数
  user_id = request.POST.get('user_id')
  department_id = request.POST.get('department_id')
  readme = request.POST.get('readme')
  # 查询
  checkOrder = order.objects.filter(patient_id=user_id,department_id=department_id,status=1).first()
  if checkOrder:
    return Action.fail("请勿重复挂号")
  checkDepartment = department.objects.filter(id=department_id).first()
  # 若没注册，添加入数据库
  newOrder = order(patient_id=user_id, department_id=department_id, readme=readme, registration_fee=checkDepartment.registration_fee,status=1)
  newOrder.save()
  return Action.success()

@api_view(['GET',"POST"])
# 就诊详情
def orderInfo(request):
  # 获取参数
  id = request.POST.get('id')
  # 查询
  checkOrder = order.objects.filter(id=id).first()
  print('checkOrder:', checkOrder)
  temp = {}
  temp['id'] = checkOrder.id
  temp['patient_id'] = checkOrder.patient_id
  temp['patient_name'] = user_patient.objects.filter(id=checkOrder.patient_id).first().name 
  temp['department_id'] = checkOrder.department_id
  temp['department_name'] = department.objects.filter(id=checkOrder.department_id).first().name
  temp['readme'] = checkOrder.readme
  temp['registration_fee'] = checkOrder.registration_fee
  temp['doctor_id'] = checkOrder.doctor_id
  temp['order_advice'] = checkOrder.order_advice
  temp['total_cost'] = checkOrder.total_cost
  temp['status'] = checkOrder.status
  temp['time'] = checkOrder.time
  return Action.success(temp)

@api_view(['GET',"POST"])
# 完成就诊
def orderFinish(request):
  # 获取参数
  id = request.POST.get('id')
  order_advice = request.POST.get('order_advice')
  medicine_list = request.POST.get('medicine_list')
  doctor_id = request.POST.get('doctor_id')
  medicine_list_arr = medicine_list.split(',')
  # 查询
  checkOrder = order.objects.filter(id=id).first()
  if checkOrder.status != 1:
    return Action.fail("该病人已处理")
  cost_sum = int(checkOrder.registration_fee)
  for de in medicine_list_arr:
    cost_sum = cost_sum + int(medicine.objects.filter(id=de).first().price)
  checkOrder.doctor_id = doctor_id
  checkOrder.order_advice = order_advice
  checkOrder.medicine_list = medicine_list
  checkOrder.status = 2
  checkOrder.total_cost = cost_sum
  checkOrder.save()
  return Action.success()