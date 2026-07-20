from django.urls import path
from . import views

app_name = 'recovery'

urlpatterns = [
    path('', views.recovery_list, name='list'),
    path('<uuid:uid>/', views.recovery_detail, name='detail'),
    path('initiate/<int:post_id>/', views.initiate_recovery, name='initiate'),
    path('<uuid:uid>/send-otp/', views.send_otp, name='send_otp'),
    path('<uuid:uid>/verify-otp/', views.verify_otp, name='verify_otp'),
    path('<uuid:uid>/generate-qr/', views.generate_qr, name='generate_qr'),
    path('<uuid:uid>/scan-qr/', views.scan_qr, name='scan_qr'),
    path('<uuid:uid>/verify-handover/', views.verify_handover, name='verify_handover'),
    path('<uuid:uid>/confirm/', views.confirm_recovery, name='confirm'),
    path('<uuid:uid>/cancel/', views.cancel_recovery, name='cancel'),
    path('admin/', views.recovery_admin_list, name='admin_list'),
]