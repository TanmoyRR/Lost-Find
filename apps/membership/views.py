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
    return render(request, 'membership/cancel.html')
