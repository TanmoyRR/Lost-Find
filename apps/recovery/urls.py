from django.urls import path
from . import views

app_name = 'recovery'

urlpatterns = [
    path('', views.recovery_list, name='list'),
    path('<str:short_code>/', views.recovery_detail, name='detail'),
    path('<str:short_code>/generate-qr/', views.generate_qr, name='generate_qr'),
    path('<str:short_code>/scan-qr/', views.scan_qr, name='scan_qr'),
    path('<str:short_code>/cancel/', views.cancel_recovery, name='cancel'),
    path('admin/', views.recovery_admin_list, name='admin_list'),
]
