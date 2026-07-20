from django.urls import path
from . import views, api_views, success_views, trust_views

app_name = 'posts'

urlpatterns = [
    path('browse/', views.browse_posts, name='browse'),
    path('post/<int:pk>/', views.post_detail, name='detail'),
    path('post/create/', views.create_post, name='create'),
    path('post/<int:pk>/edit/', views.edit_post, name='edit'),
    path('post/<int:pk>/delete/', views.delete_post, name='delete'),
    path('post/<int:pk>/resolve/', views.mark_resolved, name='resolve'),
    path('my-posts/', views.my_posts, name='my_posts'),
    path('api/posts/', api_views.api_posts, name='api_posts'),
    path('success-stories/', success_views.success_stories, name='success_stories'),
    path('success-stories/<int:pk>/', success_views.success_story_detail, name='success_story_detail'),
    path('post/<int:post_id>/report/', trust_views.report_item, name='report_item'),
]
