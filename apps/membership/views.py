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
        if not request.user.is_membership_paid:
            request.user.is_membership_paid = True
            request.user.save(update_fields=['is_membership_paid'])
        membership = getattr(request.user, 'membership', None)
        if not membership:
            membership = Membership.objects.create(
                user=request.user, is_active=True,
                started_at=timezone.now(),
                expires_at=timezone.now() + timedelta(days=30),
            )
        elif not membership.is_active:
            payment = Payment.objects.filter(
                user=request.user, payment_type='membership', status='completed'
            ).order_by('-created_at').first()
            if payment and payment.reference_id:
                try:
                    plan = MembershipPlan.objects.get(pk=payment.reference_id)
                    membership.plan = plan
                    membership.is_active = True
                    membership.started_at = membership.started_at or timezone.now()
                    membership.expires_at = (membership.expires_at if membership.expires_at and membership.expires_at > timezone.now() else timezone.now()) + timedelta(days=plan.duration_days)
                    membership.save()
                except (MembershipPlan.DoesNotExist, TypeError):
                    membership.is_active = True
                    membership.started_at = membership.started_at or timezone.now()
                    if not membership.expires_at or membership.expires_at <= timezone.now():
                        membership.expires_at = timezone.now() + timedelta(days=30)
                    membership.save()
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

    if request.user.role == 'admin':
        messages.info(request, 'Admin accounts do not need a membership.')
        return redirect('membership:manage')

    existing_completed = Payment.objects.filter(
        user=request.user, payment_type='membership', status='completed'
    ).exists()
    if existing_completed and not request.user.is_membership_paid:
        request.user.is_membership_paid = True
        request.user.save(update_fields=['is_membership_paid'])

    Payment.objects.filter(
        user=request.user, payment_type='membership', status='pending'
    ).update(status='expired')

    Membership.objects.get_or_create(user=request.user)

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
