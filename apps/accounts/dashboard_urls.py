from django.urls import path
from . import dashboard_views

app_name = 'dashboard'

urlpatterns = [
    path('dashboard/', dashboard_views.user_dashboard, name='home'),
    path('dashboard/admin/', dashboard_views.admin_dashboard, name='admin_home'),
    path('dashboard/admin/users/', dashboard_views.admin_users, name='admin_users'),
    path('dashboard/admin/users/<int:pk>/', dashboard_views.admin_user_detail, name='admin_user_detail'),
    path('dashboard/admin/users/<int:pk>/suspend/', dashboard_views.admin_suspend_user, name='admin_suspend_user'),
    path('dashboard/admin/users/<int:pk>/activate/', dashboard_views.admin_activate_user, name='admin_activate_user'),
    path('dashboard/admin/posts/', dashboard_views.admin_posts, name='admin_posts'),
    path('dashboard/admin/posts/<int:pk>/approve/', dashboard_views.admin_post_approve, name='admin_post_approve'),
    path('dashboard/admin/posts/<int:pk>/reject/', dashboard_views.admin_post_reject, name='admin_post_reject'),
    path('dashboard/admin/posts/<int:pk>/soft-delete/', dashboard_views.admin_post_soft_delete, name='admin_post_soft_delete'),
    path('dashboard/admin/posts/<int:pk>/restore/', dashboard_views.admin_post_restore, name='admin_post_restore'),
    path('dashboard/admin/posts/<int:pk>/permanent-delete/', dashboard_views.admin_post_permanent_delete, name='admin_post_permanent_delete'),
    path('dashboard/admin/categories/', dashboard_views.admin_categories, name='admin_categories'),
    path('dashboard/admin/locations/', dashboard_views.admin_locations, name='admin_locations'),
    path('dashboard/admin/payments/', dashboard_views.admin_payments, name='admin_payments'),
    path('dashboard/admin/reports/', dashboard_views.admin_reports, name='admin_reports'),
    path('dashboard/admin/analytics/', dashboard_views.admin_analytics, name='admin_analytics'),
    path('dashboard/admin/memberships/', dashboard_views.admin_memberships, name='admin_memberships'),
    path('dashboard/admin/settings/', dashboard_views.admin_settings, name='admin_settings'),
    path('dashboard/admin/users/<int:pk>/update-membership/', dashboard_views.admin_update_membership, name='admin_update_membership'),
    path('dashboard/admin/users/<int:pk>/toggle-membership/', dashboard_views.admin_toggle_membership, name='admin_toggle_membership'),
]
