from django.urls import path
from . import views

app_name = 'recovery'

urlpatterns = [
    path('', views.recovery_list, name='list'),
    path('<str:short_code>/', views.recovery_detail, name='detail'),
    path('<str:short_code>/regenerate-token/', views.regenerate_token, name='regenerate_token'),
    path('<str:short_code>/enter-token/', views.enter_token, name='enter_token'),
    path('<str:short_code>/cancel/', views.cancel_recovery, name='cancel'),
    path('admin/', views.recovery_admin_list, name='admin_list'),
]
