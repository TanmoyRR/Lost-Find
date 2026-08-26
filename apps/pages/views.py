from django.shortcuts import render
from django.db.models import Count, Q
from apps.posts.models import Post, Category, CampusLocation
from apps.accounts.models import User


def home(request):
    counts = Post.objects.aggregate(
        total_posts=Count('id'),
        resolved_posts=Count('id', filter=Q(status='resolved')),
        open_posts=Count('id', filter=Q(status='open')),
    )
    stats = {
        'total_posts': counts['total_posts'],
        'total_users': User.objects.count(),
        'resolved_posts': counts['resolved_posts'],
        'open_posts': counts['open_posts'],
    }
    recent_posts = Post.objects.select_related('location', 'category').all()[:6] if request.user.is_authenticated else []
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
