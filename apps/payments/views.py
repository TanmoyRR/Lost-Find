import json
import uuid
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from .models import Payment
from apps.membership.models import Membership, MembershipPlan
from apps.accounts.models import UserActivity


def initiate_payment(request, amount, purpose, payment_type, reference_id=None):
    tran_id = str(uuid.uuid4())[:20]

    payment = Payment.objects.create(
        user=request.user,
        amount=amount,
        payment_type=payment_type,
        status='pending',
        sslcommerz_tran_id=tran_id,
        reference_id=reference_id,
    )

    post_data = {
        'store_id': settings.SSLCOMMERZ_STORE_ID,
        'store_passwd': settings.SSLCOMMERZ_STORE_PASS,
        'total_amount': str(amount),
        'currency': 'BDT',
        'tran_id': tran_id,
        'success_url': request.build_absolute_uri(reverse('payments:success')),
        'fail_url': request.build_absolute_uri(reverse('payments:fail')),
        'cancel_url': request.build_absolute_uri(reverse('payments:cancel')),
        'cus_name': request.user.get_full_name() or request.user.username,
        'cus_email': request.user.email,
        'cus_phone': request.user.phone or 'N/A',
        'cus_add1': 'IUBAT University',
        'cus_city': 'Dhaka',
        'cus_country': 'Bangladesh',
        'product_name': purpose,
        'product_category': 'Membership',
        'product_profile': 'general',
    }

    # Development fallback: skip SSLCommerz if using demo/dev credentials
    if settings.SSLCOMMERZ_STORE_ID in ('', 'demo') or settings.SSLCOMMERZ_STORE_PASS in ('', 'demo'):
        payment.status = 'completed'
        payment.transaction_id = f'DEV-{tran_id}'
        payment.save()

        membership, _ = Membership.objects.get_or_create(user=request.user)
        plan = MembershipPlan.objects.filter(is_active=True).first()
        if plan:
            membership.plan = plan
            membership.is_active = True
            membership.started_at = timezone.now()
            membership.expires_at = timezone.now() + timedelta(days=plan.duration_days)
            membership.save()

        UserActivity.objects.create(
            user=request.user,
            activity_type='membership_purchased',
            description=f'Membership purchased for {amount} BDT (dev mode)'
        )

        messages.success(request, 'Membership activated successfully! (Development mode)')
        return redirect('membership:success')

    try:
        response = requests.post(f'{settings.SSLCOMMERZ_BASE_URL}/gwprocess/v4/api.php', data=post_data)
        result = response.json()
        if result.get('status') == 'SUCCESS':
            payment.sslcommerz_session = json.dumps(result)
            payment.save()
            return redirect(result['GatewayPageURL'])
        else:
            payment.status = 'failed'
            payment.save()
            messages.error(request, 'Payment initiation failed.')
            return redirect('membership:index')
    except Exception as e:
        payment.status = 'failed'
        payment.save()
        messages.error(request, f'Payment error: {str(e)}')
        return redirect('membership:index')


@csrf_exempt
def payment_success(request):
    if request.method == 'POST':
        tran_id = request.POST.get('tran_id')
        try:
            payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
            payment.status = 'completed'
            payment.transaction_id = request.POST.get('bank_tran_id', '')
            payment.save()

            membership, _ = Membership.objects.get_or_create(user=payment.user)
            plan = MembershipPlan.objects.filter(is_active=True).first()
            if plan:
                membership.plan = plan
                membership.is_active = True
                membership.started_at = timezone.now()
                membership.expires_at = timezone.now() + timedelta(days=plan.duration_days)
                membership.save()

            UserActivity.objects.create(
                user=payment.user,
                activity_type='membership_purchased',
                description=f'Membership purchased for {payment.amount} BDT'
            )

            return redirect('membership:success')
        except Payment.DoesNotExist:
            return redirect('membership:index')


@csrf_exempt
def payment_fail(request):
    tran_id = request.POST.get('tran_id', '')
    try:
        payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
        payment.status = 'failed'
        payment.save()
    except Payment.DoesNotExist:
        pass
    messages.error(request, 'Payment failed. Please try again.')
    return redirect('membership:index')


@csrf_exempt
def payment_cancel(request):
    tran_id = request.POST.get('tran_id', '')
    try:
        payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
        payment.status = 'cancelled'
        payment.save()
    except Payment.DoesNotExist:
        pass
    messages.warning(request, 'Payment was cancelled.')
    return redirect('membership:index')
