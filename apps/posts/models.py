"""
Post Models — Core data models for the Lost & Found item system.

This module defines the database schema for:
  - Category: Item categories (e.g., Electronics, Books, ID Cards)
  - CampusLocation: Physical locations within the IUBAT campus
  - Post: The central model — represents a lost or found item listing
  - PostImage: Additional gallery images for a post (beyond the primary image)
  - PostTag: Searchable tags attached to posts
  - SuccessStory: Recovery stories published on the platform
  - TrustReport: User-submitted abuse/spam reports against posts or users
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Category(models.Model):
    """
    Item category for organizing posts (e.g., Electronics, Documents, Clothing).

    Each category has a unique slug used in URL filtering on the browse page.
    Categories can be deactivated by admins without deleting them.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, default='bi-tag')  # Bootstrap icon class
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class CampusLocation(models.Model):
    """
    Physical location within IUBAT campus where items were lost/found.

    Used for location-based filtering on the browse page.
    Each location can optionally specify building and floor details.
    """
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
    """
    Central model — represents a lost or found item listing.

    Post lifecycle (status flow):
      open → claimed → resolved
                     → rejected (admin action)
                     → closed (admin action or timeout)

    Two types of posts:
      - 'lost': Created by someone who lost an item. A recovery token is auto-generated.
      - 'found': Created by someone who found an item. The finder enters the owner's token.

    Key relationships:
      - user: The person who created the post
      - matched_post: Links to the paired lost/found post after AI matching or recovery
      - category, location: For filtering and search

    AI integration:
      - After creation/editing, an embedding is generated via Jina API
      - The embedding is stored in PostEmbedding (OneToOne) for semantic search
      - MatchSuggestion records link this post to potential matches
    """

    POST_TYPES = (
        ('lost', 'Lost'),
        ('found', 'Found'),
    )
    STATUS_CHOICES = (
        ('open', 'Open'),         # Active, awaiting match
        ('claimed', 'Claimed'),   # Matched with another post, recovery in progress
        ('resolved', 'Resolved'), # Item recovered, post hidden from browse
        ('rejected', 'Rejected'), # Admin rejected the post
        ('closed', 'Closed'),     # Post closed by admin or timeout
    )

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='posts')
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='posts')
    location = models.ForeignKey(CampusLocation, on_delete=models.SET_NULL, null=True, related_name='posts')
    location_name = models.CharField(max_length=200, blank=True, null=True)  # Free-text fallback if no CampusLocation match
    post_type = models.CharField(max_length=10, choices=POST_TYPES)
    date_lost_found = models.DateField()  # When the item was lost or found
    image = models.ImageField(upload_to='posts/', null=True, blank=True)  # Primary image (required for found posts)
    contact_info = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    is_resolved = models.BooleanField(default=False)  # Auto-synced in save() based on status
    is_active = models.BooleanField(default=True)
    views_count = models.PositiveIntegerField(default=0)
    matched_post = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='matched_by', verbose_name='Matched Post',
        help_text='The Lost/Found post this item has been matched with through recovery token verification.',
    )
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
        """Return the CampusLocation name, or fall back to free-text location_name."""
        if self.location:
            return self.location.name
        return self.location_name or 'N/A'

    def save(self, *args, **kwargs):
        """
        Custom save: auto-sync is_resolved flag and log new post creation.

        is_resolved is always kept in sync with status == 'resolved'.
        For new posts, a UserActivity record is created to track the action.
        """
        self.is_resolved = (self.status == 'resolved')
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
    """
    Additional gallery images for a post (beyond the primary Post.image).

    Each post can have multiple gallery images. One image per post can be
    marked as 'primary' (enforced by UniqueConstraint). Primary images are
    displayed first in the gallery.
    """
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='posts/gallery/')
    caption = models.CharField(max_length=200, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Post Image'
        verbose_name_plural = 'Post Images'
        ordering = ['-is_primary', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['post'],
                condition=models.Q(is_primary=True),
                name='unique_primary_image_per_post',
            ),
        ]

    def clean(self):
        """Validate that only one image per post is marked as primary."""
        if self.is_primary:
            existing = PostImage.objects.filter(
                post=self.post, is_primary=True
            ).exclude(pk=self.pk)
            if existing.exists():
                from django.core.exceptions import ValidationError
                raise ValidationError('Only one image can be marked as primary per post.')

    def __str__(self):
        return f"Image for {self.post.title[:30]}"


class PostTag(models.Model):
    """Searchable tag attached to a post (e.g., 'blue', 'laptop', 'urgent')."""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Post Tag'
        verbose_name_plural = 'Post Tags'
        constraints = [
            models.UniqueConstraint(fields=['post', 'name'], name='unique_post_tag'),
        ]

    def __str__(self):
        return self.name


class SuccessStory(models.Model):
    """
    Published recovery story — showcased on the success stories page.

    Links to a resolved Post and includes quotes from both the finder and owner.
    Admins can feature stories on the homepage.
    """
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
    """
    User-submitted report against a post or user for moderation.

    Report types: spam, fake listing, harassment, scam, duplicate, other.
    Reports are reviewed by admins who can mark them as investigated,
    resolved, or dismissed.
    """
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
