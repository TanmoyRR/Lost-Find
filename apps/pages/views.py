import logging
from django.shortcuts import render
from django.contrib import messages
from django.db.models import Count, Q
from apps.posts.models import Post, Category, CampusLocation
from apps.accounts.models import User

logger = logging.getLogger(__name__)


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
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()

        if not name or not email or not message:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'pages/contact.html', {
                'form_name': name,
                'form_email': email,
                'form_subject': subject,
                'form_message': message,
            })

        # Log the contact form submission
        logger.info(
            'Contact form submission: name=%s, email=%s, subject=%s',
            name, email, subject,
        )

        # Send email to admin
        from django.core.mail import send_mail
        from django.conf import settings
        try:
            send_mail(
                subject=f'Contact Form: {subject or "No Subject"}',
                message=f'From: {name} ({email})\n\n{message}',
                from_email=email,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],
                fail_silently=False,
            )
            messages.success(request, 'Your message has been sent successfully! We will get back to you soon.')
        except Exception as e:
            logger.error('Failed to send contact email: %s', e)
            messages.success(request, 'Your message has been received. We will get back to you soon.')

        return render(request, 'pages/contact.html')

    return render(request, 'pages/contact.html')
