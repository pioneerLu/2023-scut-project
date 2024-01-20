from django.shortcuts import render

# 页面渲染
#登陆页面
def login(request):
  return render(request, 'login.html')

#管理员页面: 科室管理
def admin_department(request):
  return render(request, 'admin_department.html')

#管理员页面: 医生管理
def admin_doctor(request):
  return render(request, 'admin_doctor.html')

#管理员页面: 药品管理
def admin_medicine(request):
  return render(request, 'admin_medicine.html')

#管理员页面: 患者管理
def admin_patient(request):
  return render(request, 'admin_patient.html')


#患者页面: 大厅
def patient_home(request):
  return render(request, 'patient_home.html')

#患者页面: 就诊记录
def patient_order(request):
  return render(request, 'patient_order.html')


#医生页面: 接诊房间
def doctor_home(request):
  return render(request, 'doctor_home.html')

#患者页面: 接诊记录
def doctor_order(request):
  return render(request, 'doctor_order.html')