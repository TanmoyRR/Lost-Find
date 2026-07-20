from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserActivity


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'role', 'student_id', 'department', 'is_verified', 'is_active', 'is_suspended', 'date_joined']
    list_filter = ['role', 'is_verified', 'is_active', 'is_suspended', 'department']
    search_fields = ['username', 'email', 'student_id', 'phone']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extra Info', {'fields': ('role', 'student_id', 'department', 'phone', 'profile_picture', 'is_verified', 'is_suspended', 'email_verified')}),
    )


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'description', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['user__username', 'description']
