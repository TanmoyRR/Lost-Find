from django.http import JsonResponse
from django.db.models import Q
from .models import Post, Category, CampusLocation


def api_posts(request):
    query = request.GET.get('q', '')
    post_type = request.GET.get('type', '')
    category = request.GET.get('category', '')
    location = request.GET.get('location', '')
    status = request.GET.get('status', '')

    posts = Post.objects.filter(status='open')

    if query:
        posts = posts.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )
    if post_type:
        posts = posts.filter(post_type=post_type)
    if category:
        posts = posts.filter(category__slug=category)
    if location:
        posts = posts.filter(location__slug=location)
    if status:
        posts = posts.filter(status=status)

    data = {
        'count': posts.count(),
        'posts': [
            {
                'id': p.pk,
                'title': p.title,
                'description': p.description[:150],
                'type': p.post_type,
                'status': p.status,
                'location': p.location.name if p.location else None,
                'date': p.created_at.strftime('%b %d, %Y'),
                'image': p.image.url if p.image else None,
            }
            for p in posts[:50]
        ],
    }
    return JsonResponse(data)
