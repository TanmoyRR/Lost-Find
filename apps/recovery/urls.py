from django.urls import path
from . import views

app_name = 'recovery'

urlpatterns = [
    path('', views.recovery_list, name='list'),
    path('admin/', views.recovery_admin_list, name='admin_list'),
    path('admin/<str:short_code>/force-complete/', views.admin_force_complete, name='admin_force_complete'),
    path('admin/<str:short_code>/force-cancel/', views.admin_force_cancel, name='admin_force_cancel'),
    path('admin/<str:short_code>/reassign/', views.admin_reassign_claimant, name='admin_reassign_claimant'),
    path('<str:short_code>/', views.recovery_detail, name='detail'),
    path('<str:short_code>/regenerate-token/', views.regenerate_token, name='regenerate_token'),
    path('<str:short_code>/enter-token/', views.enter_token, name='enter_token'),
    path('<str:short_code>/cancel/', views.cancel_recovery, name='cancel'),
]
