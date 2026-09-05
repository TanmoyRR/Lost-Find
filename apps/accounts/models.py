from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
import uuid


class User(AbstractUser):
    USER_ROLES = (
        ('guest', 'Guest'),
        ('student', 'Student'),
        ('admin', 'Admin'),
    )

    DEPARTMENTS = (
        ('cse', 'Computer Science & Engineering'),
        ('eee', 'Electrical & Electronic Engineering'),
        ('ce', 'Civil Engineering'),
        ('me', 'Mechanical Engineering'),
        ('bba', 'Business Administration'),
        ('english', 'English'),
        ('law', 'Law'),
        ('pharmacy', 'Pharmacy'),
        ('nursing', 'Nursing'),
        ('textile', 'Textile Engineering'),
    )

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    role = models.CharField(max_length=20, choices=USER_ROLES, default='student')
    student_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=50, choices=DEPARTMENTS, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    cover_photo = models.ImageField(upload_to='covers/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    social_links = models.JSONField(default=dict, blank=True)
    reputation_score = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_suspended = models.BooleanField(default=False)
    is_membership_paid = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=255, null=True, blank=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    reset_password_token = models.CharField(max_length=255, null=True, blank=True)
    reset_password_sent_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

    def is_member(self):
        return hasattr(self, 'membership') and self.membership.is_active

    def total_posts(self):
        return self.posts.count()

    def open_posts(self):
        return self.posts.filter(status='open').count()

    def resolved_posts(self):
        return self.posts.filter(status='resolved').count()

    def lost_posts(self):
        return self.posts.filter(post_type='lost').count()

    def found_posts(self):
        return self.posts.filter(post_type='found').count()


class UserActivity(models.Model):
    ACTIVITY_TYPES = (
        ('post_created', 'Post Created'),
        ('post_updated', 'Post Updated'),
        ('post_resolved', 'Post Resolved'),
        ('post_deleted', 'Post Deleted'),
        ('membership_purchased', 'Membership Purchased'),
        ('membership_expired', 'Membership Expired'),
        ('profile_updated', 'Profile Updated'),
        ('password_changed', 'Password Changed'),
        ('login', 'Login'),
        ('match_found', 'Match Found'),
    )

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'activity_type'], name='activity_user_type_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_activity_type_display()}"
