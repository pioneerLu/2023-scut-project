"""hospital URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# from django.contrib import admin
from hospital import view_admin
from hospital import view_patient
from hospital import view_doctor
from hospital import view_medicine
from hospital import view_department
from hospital import view_order
from hospital import views_super

from django.urls import path
from django.conf.urls import url
from . import views
from django.views.generic import RedirectView
urlpatterns = [
    #空路径重定向
    path('', RedirectView.as_view(url='/login/')),
    #页面请求
    path('login/', views.login),
    path('admin/', views.admin_department),
    path('admin_department/', views.admin_department),
    path('admin_doctor/', views.admin_doctor),
    path('admin_medicine/', views.admin_medicine),
    path('admin_patient/', views.admin_patient),

    path('patient/', views.patient_home),
    path('patient_home/', views.patient_home),
    path('patient_order/', views.patient_order),

    path('doctor/', views.doctor_order),
    path('doctor_home/', views.doctor_home),
    path('doctor_order/', views.doctor_order),

    #数据请求

    #管理员
    path('adminLogin', view_admin.adminLogin, name='adminLogin'),
    path('departmentList', view_department.departmentList, name='departmentList'),
    path('doctorList', view_doctor.doctorList, name='doctorList'),
    path('doctorAdd', view_doctor.doctorAdd, name='doctorAdd'),
    path('patientList', view_patient.patientList, name='patientList'),
    path('patientAdd', view_patient.patientRegister, name='patientAdd'),
    path('mark_super_doctor', views_super.mark_super_doctor, name='mark_super_doctor'),
    path('mark_special_patient', views_super.mark_special_patient, name='mark_special_patient'),
    # 药品
    path('medicineList', view_medicine.medicineList, name='medicineList'),
    path('medicineStrList', view_medicine.medicineStrList, name='medicineStrList'),
    path('medicineAdd', view_medicine.medicineAdd, name='medicineAdd'),
    #患者
    path('patientRegister', view_patient.patientRegister, name='patientRegister'),
    path('patientLogin', view_patient.patientLogin, name='patientLogin'),
    # 就诊
    path('orderAdd', view_order.orderAdd, name='orderAdd'),
    path('orderList', view_order.orderList, name='orderList'),
    path('orderInfo', view_order.orderInfo, name='orderInfo'),
    path('orderFinish', view_order.orderFinish, name='orderFinish'),

    #医生
    path('doctorLogin', view_doctor.doctorLogin, name='doctorLogin'),
]
