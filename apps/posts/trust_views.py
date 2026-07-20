from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from .models import TrustReport, Post

@login_required
def report_item(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if request.method == 'POST':
        report_type = request.POST.get('report_type')
        description = request.POST.get('description', '')
        if not report_type:
            messages.error(request, 'Please select a report type.')
            return redirect('posts:detail', pk=post_id)
        TrustReport.objects.create(
            reporter=request.user,
            reported_user=post.user,
            post=post,
            report_type=report_type,
            description=description,
        )
        messages.success(request, 'Report submitted. Our team will review it shortly.')
        return redirect('posts:detail', pk=post_id)
    return render(request, 'posts/report_form.html', {'post': get_object_or_404(Post, pk=post_id)})