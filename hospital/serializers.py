from rest_framework import serializers
from .models import *


# 对数据进行序列化
# 患者数据序列化
class AdminSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = admin
        fields = ['id', 'name', 'password']

# 患者数据序列化
class UserPatientSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = user_patient
        fields = ['id', 'name', 'id_card', 'phone', 'password', 'sex', 'age']

# 医生数据序列化
class UserDoctorSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = user_doctor
        fields = ['id', 'name', 'id_card', 'department_id', 'password', 'status']

# 科室数据序列化
class DepartmentSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = department
        fields = ['id', 'name', 'registration_fee', 'doctor_num']

# 药品数据序列化
class MedicineSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = medicine
        fields = ['id', 'name', 'price', 'unit']

# 挂号
class OrderSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = order
        fields = ['id', 'patient_id', 'department_id', 'readme', 'registration_fee', 'doctor_id', 'order_advice', 'medicine_list', 'total_cost', 'status', 'time']
