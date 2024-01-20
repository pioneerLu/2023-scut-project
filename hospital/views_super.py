from django.shortcuts import render, redirect
from .models import user_doctor, user_patient
from .Action import Action
from rest_framework.decorators import api_view

@api_view(['GET',"POST"])
def mark_super_doctor(request):
    print("1111")
    if request.method == 'POST':
        doctor_ids = request.POST.getlist('doctor_ids')
        user_doctor.objects.filter(id__in=doctor_ids).update(is_super_doctor=True)
    return Action.success()
@api_view(['GET',"POST"])
def mark_special_patient(request):
    if request.method == 'POST':
        patient_ids = request.POST.getlist('patient_ids')
        user_patient.objects.filter(id__in=patient_ids).update(is_special_patient=True)
    return Action.success()
