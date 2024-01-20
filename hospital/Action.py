from django.http import JsonResponse
from .models import *

class Action:
  # 成功数据请求的返回模板
  def success(data = ''):
    return JsonResponse({"code": 0, "data": data}, safe=False)
  # 失败数据请求的返回模板
  def fail(data = ''):
    return JsonResponse({"code": -1, "data": data}, safe=False)