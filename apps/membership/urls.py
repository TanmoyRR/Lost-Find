from django.urls import path
from . import views

app_name = 'membership'

urlpatterns = [
    path('', views.membership_view, name='index'),
    path('purchase/<int:plan_id>/', views.purchase_membership, name='purchase'),
    path('success/', views.membership_success, name='success'),
    path('cancel/', views.membership_cancel, name='cancel'),
]
