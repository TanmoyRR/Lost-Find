from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Count, Q
from .models import TrustReport, Post
from apps.notifications.models import Notification
from apps.accounts.models import User

@login_required
def report_item(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if request.method == 'POST':
        report_type = request.POST.get('report_type')
        description = request.POST.get('description', '')
        if not report_type:
            messages.error(request, 'Please select a report type.')
            return redirect('posts:detail', pk=post_id)
        report = TrustReport.objects.create(
            reporter=request.user,
            reported_user=post.user,
            post=post,
            report_type=report_type,
            description=description,
        )
        try:
            for admin in User.objects.filter(role='admin'):
                Notification.objects.create(
                    notification_type='system',
                    title='Someone reported a post — please check',
                    message=f'{report_type}: {description[:80]} — "{post.title}"',
                    link=reverse('dashboard:admin_report_detail', args=[report.pk]),
                    user=admin,
                )
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Failed to create admin notification for report %s', report.pk)
        messages.success(request, 'Report submitted. Our team will review it shortly.')
        return redirect('posts:detail', pk=post_id)
    return render(request, 'posts/report_form.html', {'post': post})