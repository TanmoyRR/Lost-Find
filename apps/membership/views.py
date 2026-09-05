from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import hashlib
import secrets

from .models import Membership, MembershipPlan
from apps.payments.models import Payment
from apps.accounts.models import UserActivity


@login_required
def pending_membership_purchase(request):
    if request.user.role == 'admin' or request.user.is_membership_paid:
        return redirect('dashboard:home')

    plans = MembershipPlan.objects.filter(is_active=True)
    has_pending_payment = Payment.objects.filter(
        user=request.user, payment_type='membership', status='pending'
    ).exists()
    has_completed_payment = Payment.objects.filter(
        user=request.user, payment_type='membership', status='completed'
    ).exists()

    if has_completed_payment:
        return redirect('membership:success')

    return render(request, 'membership/pending_purchase.html', {
        'plans': plans,
        'has_pending_payment': has_pending_payment,
    })


@login_required
def membership_view(request):
    membership = getattr(request.user, 'membership', None)
    plans = MembershipPlan.objects.filter(is_active=True)
    return render(request, 'membership/index.html', {
        'membership': membership,
        'plans': plans,
    })


@login_required
def purchase_membership(request, plan_id):
    plan = get_object_or_404(MembershipPlan, pk=plan_id, is_active=True)
    existing_pending = Payment.objects.filter(
        user=request.user, payment_type='membership', status='pending'
    ).exists()
    if existing_pending:
        messages.warning(request, 'You already have a pending payment. Please complete it first.')
        return redirect('membership:pending_purchase')
    membership, created = Membership.objects.get_or_create(user=request.user)
    membership.plan = plan
    membership.save()

    from apps.payments.views import initiate_payment
    return initiate_payment(request, plan.price, f'Membership - {plan.name}', 'membership', plan_id)


@login_required
def membership_success(request):
    membership = getattr(request.user, 'membership', None)
    payment = Payment.objects.filter(user=request.user, status='completed').order_by('-created_at').first()
    return render(request, 'membership/success.html', {
        'membership': membership,
        'payment': payment,
    })


@login_required
def membership_cancel(request):
    if not request.user.is_membership_paid and request.user.role != 'admin':
        return redirect('membership:pending_purchase')
    return render(request, 'membership/cancel.html')


@login_required
def manage_membership(request):
    membership = getattr(request.user, 'membership', None)
    payments = Payment.objects.filter(user=request.user, payment_type='membership').order_by('-created_at')[:10]
    plans = MembershipPlan.objects.filter(is_active=True)
    return render(request, 'membership/manage.html', {
        'membership': membership,
        'payments': payments,
        'plans': plans,
    })
