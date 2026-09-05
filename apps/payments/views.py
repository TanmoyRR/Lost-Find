import json
import uuid
import logging
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from decimal import Decimal

from .models import Payment
from apps.membership.models import Membership, MembershipPlan
from apps.accounts.models import UserActivity

logger = logging.getLogger(__name__)

SSLCOMMERZ_VALIDATION_URL = {
    True: 'https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php',
    False: 'https://secure.sslcommerz.com/validator/api/validationserverAPI.php',
}


def verify_sslcommerz_payment(val_id):
    """Verify a payment with SSLCommerz using val_id (IPN validation)."""
    url = SSLCOMMERZ_VALIDATION_URL[settings.SSLCOMMERZ_IS_SANDBOX]
    payload = {
        'val_id': val_id,
        'store_id': settings.SSLCOMMERZ_STORE_ID,
        'store_passwd': settings.SSLCOMMERZ_STORE_PASS,
    }
    try:
        resp = requests.post(url, data=payload, timeout=30)
        result = resp.json()
        logger.info('SSLCommerz validation response status: %s', result.get('status'))
        return result
    except Exception as e:
        logger.error('SSLCommerz validation error: %s', e)
        return None


def _validate_payment_result(result, payment):
    """Validate SSLCommerz verification result against our payment record.

    Returns (is_valid, error_message).
    """
    if result.get('status') != 'VALID':
        logger.warning(
            'Payment validation failed: status=%s for tran_id=%s',
            result.get('status'), payment.sslcommerz_tran_id,
        )
        return False, 'Payment verification failed.'

    # Verify amount matches (only if amount is present in the response)
    returned_amount = result.get('amount')
    if returned_amount is not None:
        try:
            returned_amount = Decimal(str(returned_amount))
            if returned_amount != payment.amount:
                logger.warning(
                    'Payment amount mismatch: expected %s, got %s for tran_id=%s',
                    payment.amount, returned_amount, payment.sslcommerz_tran_id,
                )
                return False, 'Payment amount mismatch.'
        except (ValueError, TypeError) as e:
            logger.error('Payment amount parsing error: %s', e)
            return False, 'Invalid payment amount.'

    # Verify currency (only if currency is present in the response)
    currency = result.get('currency')
    if currency and currency.upper() != 'BDT':
        logger.warning(
            'Payment currency mismatch: expected BDT, got %s for tran_id=%s',
            currency, payment.sslcommerz_tran_id,
        )
        return False, 'Invalid payment currency.'

    # Verify transaction ID matches (only if tran_id is in the response)
    returned_tran_id = result.get('tran_id')
    if returned_tran_id and returned_tran_id != payment.sslcommerz_tran_id:
        logger.warning(
            'Transaction ID mismatch: expected %s, got %s',
            payment.sslcommerz_tran_id, returned_tran_id,
        )
        return False, 'Transaction ID mismatch.'

    # Verify store_id (only if store_id is in the response)
    returned_store = result.get('store_id')
    if returned_store and returned_store != settings.SSLCOMMERZ_STORE_ID:
        logger.warning(
            'Store ID mismatch: expected %s, got %s',
            settings.SSLCOMMERZ_STORE_ID, returned_store,
        )
        return False, 'Store ID mismatch.'

    return True, ''


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
            # Extend from current expiry if still active, otherwise start fresh
            base_time = membership.expires_at if membership.is_active and membership.expires_at and membership.expires_at > timezone.now() else timezone.now()
            membership.started_at = membership.started_at or timezone.now()
            membership.expires_at = base_time + timedelta(days=plan.duration_days)
            membership.save()

        if not request.user.is_membership_paid:
            request.user.is_membership_paid = True
            request.user.save(update_fields=['is_membership_paid'])

        UserActivity.objects.create(
            user=request.user,
            activity_type='membership_purchased',
            description=f'Membership purchased for {amount} BDT (dev mode)'
        )

        messages.success(request, 'Membership activated successfully! (Development mode)')
        return redirect('membership:success')

    try:
        response = requests.post(
            f'{settings.SSLCOMMERZ_BASE_URL}/gwprocess/v4/api.php',
            data=post_data,
            timeout=30,
        )
        result = response.json()
        if result.get('status') == 'SUCCESS':
            payment.sslcommerz_session = json.dumps(result)
            payment.save()
            return redirect(result['GatewayPageURL'])
        else:
            logger.warning('SSLCommerz initiation failed: %s', result.get('failedreason', 'unknown'))
            payment.status = 'failed'
            payment.save()
            messages.error(request, 'Payment initiation failed. Please try again.')
            return redirect('membership:index')
    except Exception as e:
        logger.error('SSLCommerz initiation error: %s', e)
        payment.status = 'failed'
        payment.save()
        messages.error(request, 'Payment service temporarily unavailable. Please try again later.')
        return redirect('membership:index')


@csrf_exempt
def payment_success(request):
    """SSLCommerz IPN callback. Validated server-side via SSLCommerz API."""
    if request.method != 'POST':
        return redirect('membership:index')

    val_id = request.POST.get('val_id')
    tran_id = request.POST.get('tran_id')

    if not val_id or not tran_id:
        logger.warning('Payment callback missing val_id or tran_id')
        return redirect('membership:index')

    # Verify payment with SSLCommerz server
    result = verify_sslcommerz_payment(val_id)
    if result is None:
        logger.error('SSLCommerz verification unreachable for tran_id=%s', tran_id)
        messages.error(request, 'Could not verify payment. Please contact support.')
        return redirect('membership:index')

    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(sslcommerz_tran_id=tran_id)
    except Payment.DoesNotExist:
        logger.error('Payment callback for unknown tran_id: %s', tran_id)
        return redirect('membership:index')

    # Validate result against our payment record
    is_valid, error_msg = _validate_payment_result(result, payment)
    if not is_valid:
        logger.warning('Payment validation failed for tran_id=%s: %s', tran_id, error_msg)
        messages.error(request, 'Payment verification failed. Please contact support if you were charged.')
        return redirect('membership:index')

    # Already completed - just ensure membership is set
    if payment.status == 'completed':
        if not payment.user.is_membership_paid:
            payment.user.is_membership_paid = True
            payment.user.save(update_fields=['is_membership_paid'])
        return redirect('membership:success')

    # Only allow transition from pending
    if payment.status != 'pending':
        logger.warning(
            'Payment status transition rejected: current=%s, tran_id=%s',
            payment.status, tran_id,
        )
        messages.error(request, 'Payment cannot be processed.')
        return redirect('membership:index')

    payment.status = 'completed'
    payment.transaction_id = result.get('bank_tran_id', '')
    payment.sslcommerz_session = json.dumps(result)
    payment.save()

    membership, _ = Membership.objects.get_or_create(user=payment.user)
    plan = MembershipPlan.objects.filter(is_active=True).first()
    if plan:
        membership.plan = plan
        membership.is_active = True
        # Extend from current expiry if still active, otherwise start fresh
        base_time = membership.expires_at if membership.is_active and membership.expires_at and membership.expires_at > timezone.now() else timezone.now()
        membership.started_at = membership.started_at or timezone.now()
        membership.expires_at = base_time + timedelta(days=plan.duration_days)
        membership.save()

    if not payment.user.is_membership_paid:
        payment.user.is_membership_paid = True
        payment.user.save(update_fields=['is_membership_paid'])

    UserActivity.objects.create(
        user=payment.user,
        activity_type='membership_purchased',
        description=f'Membership purchased for {payment.amount} BDT'
    )

    logger.info('Payment completed successfully: tran_id=%s, user=%s', tran_id, payment.user.username)
    return redirect('membership:success')


@csrf_exempt
def payment_fail(request):
    """SSLCommerz fail callback."""
    tran_id = request.POST.get('tran_id') or request.GET.get('tran_id', '')
    if tran_id:
        try:
            payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
            if payment.status == 'pending':
                payment.status = 'failed'
                payment.save()
                logger.info('Payment marked as failed: tran_id=%s', tran_id)
            else:
                logger.warning(
                    'Fail callback ignored for non-pending payment: status=%s, tran_id=%s',
                    payment.status, tran_id,
                )
        except Payment.DoesNotExist:
            logger.warning('Fail callback for unknown tran_id: %s', tran_id)
    messages.error(request, 'Payment failed. Please try again.')
    return redirect('membership:index')


@csrf_exempt
def payment_cancel(request):
    """SSLCommerz cancel callback."""
    tran_id = request.POST.get('tran_id') or request.GET.get('tran_id', '')
    if tran_id:
        try:
            payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
            if payment.status == 'pending':
                payment.status = 'cancelled'
                payment.save()
                logger.info('Payment cancelled: tran_id=%s', tran_id)
            else:
                logger.warning(
                    'Cancel callback ignored for non-pending payment: status=%s, tran_id=%s',
                    payment.status, tran_id,
                )
        except Payment.DoesNotExist:
            logger.warning('Cancel callback for unknown tran_id: %s', tran_id)
    messages.warning(request, 'Payment was cancelled.')
    return redirect('membership:index')
