from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<str:token>/', views.reset_password, name='reset_password'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/edit/', views.profile_edit, name='edit_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('settings/', views.settings_view, name='settings'),
    path('profile/delete/', views.delete_account, name='delete_account'),
]
