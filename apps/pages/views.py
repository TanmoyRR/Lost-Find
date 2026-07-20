from django.shortcuts import render
from django.db.models import Count
from apps.posts.models import Post, Category, CampusLocation
from apps.accounts.models import User


def home(request):
    stats = {
        'total_posts': Post.objects.count(),
        'total_users': User.objects.count(),
        'resolved_posts': Post.objects.filter(status='resolved').count(),
        'open_posts': Post.objects.filter(status='open').count(),
    }
    recent_posts = Post.objects.all()[:6]
    categories = Category.objects.all()
    return render(request, 'pages/home.html', {
        'stats': stats,
        'recent_posts': recent_posts,
        'categories': categories,
    })


def about(request):
    return render(request, 'pages/about.html')


def contact(request):
    return render(request, 'pages/contact.html')
