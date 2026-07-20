from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from .models import SuccessStory, Post

def success_stories(request):
    stories = SuccessStory.objects.filter(is_published=True).order_by('-is_featured', '-published_at')
    featured = stories.filter(is_featured=True)[:3]
    total_recovered = SuccessStory.objects.filter(is_published=True).count()
    return render(request, 'posts/success_stories.html', {
        'stories': stories,
        'featured': featured,
        'total_recovered': total_recovered,
    })

def success_story_detail(request, pk):
    story = get_object_or_404(SuccessStory, pk=pk, is_published=True)
    return render(request, 'posts/success_story_detail.html', {'story': story})