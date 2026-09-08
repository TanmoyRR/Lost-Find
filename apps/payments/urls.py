from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('success/', views.payment_success, name='success'),
    path('fail/', views.payment_fail, name='fail'),
    path('cancel/', views.payment_cancel, name='cancel'),
    path('notify/', views.payment_notify, name='notify'),
    path('invoice/<int:payment_id>/', views.download_invoice, name='download_invoice'),
]
