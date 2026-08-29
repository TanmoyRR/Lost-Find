from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, default='bi-tag')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class CampusLocation(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    building = models.CharField(max_length=100, blank=True, null=True)
    floor = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Campus Location'
        verbose_name_plural = 'Campus Locations'
        ordering = ['name']

    def __str__(self):
        return self.name


class Post(models.Model):
    POST_TYPES = (
        ('lost', 'Lost'),
        ('found', 'Found'),
    )
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('claimed', 'Claimed'),
        ('resolved', 'Resolved'),
    )

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='posts')
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='posts')
    location = models.ForeignKey(CampusLocation, on_delete=models.SET_NULL, null=True, related_name='posts')
    location_name = models.CharField(max_length=200, blank=True, null=True)
    post_type = models.CharField(max_length=10, choices=POST_TYPES)
    date_lost_found = models.DateField()
    image = models.ImageField(upload_to='posts/', null=True, blank=True)
    contact_info = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    is_resolved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'post_type'], name='post_status_type_idx'),
            models.Index(fields=['user', 'status'], name='post_user_status_idx'),
            models.Index(fields=['-created_at'], name='post_created_idx'),
            models.Index(fields=['category', 'status'], name='post_category_status_idx'),
            models.Index(fields=['location', 'status'], name='post_location_status_idx'),
        ]

    def __str__(self):
        return f"{self.get_post_type_display()}: {self.title}"

    @property
    def display_location(self):
        if self.location:
            return self.location.name
        return self.location_name or 'N/A'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            from apps.accounts.models import UserActivity
            UserActivity.objects.create(
                user=self.user,
                activity_type='post_created',
                description=f'Created {self.get_post_type_display()} post: {self.title}'
            )


class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='posts/gallery/')
    caption = models.CharField(max_length=200, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Post Image'
        verbose_name_plural = 'Post Images'
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"Image for {self.post.title[:30]}"


class PostTag(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Post Tag'
        verbose_name_plural = 'Post Tags'
        unique_together = ['post', 'name']

    def __str__(self):
        return self.name


class SuccessStory(models.Model):
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='success_story')
    title = models.CharField(max_length=200)
    story = models.TextField()
    finder_name = models.CharField(max_length=100)
    owner_name = models.CharField(max_length=100)
    finder_message = models.TextField(blank=True, null=True)
    owner_message = models.TextField(blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Success Story'
        verbose_name_plural = 'Success Stories'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class TrustReport(models.Model):
    REPORT_TYPES = (
        ('spam', 'Spam'),
        ('fake', 'Fake Listing'),
        ('harassment', 'Harassment'),
        ('scam', 'Scam / Fraud'),
        ('duplicate', 'Duplicate'),
        ('other', 'Other'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    )

    reporter = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='reports_made')
    reported_user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='reports_received', null=True, blank=True)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True, related_name='reports')
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    resolution_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Trust Report'
        verbose_name_plural = 'Trust Reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='report_status_idx'),
        ]

    def __str__(self):
        return f"{self.get_report_type_display()} - {self.created_at.date()}"
