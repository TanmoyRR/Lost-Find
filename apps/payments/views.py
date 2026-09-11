import json
import uuid
import logging
import requests
from io import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
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

    # Verify amount matches (fail-closed if missing)
    returned_amount = result.get('amount')
    if returned_amount is None:
        logger.warning('Payment verification missing amount for tran_id=%s', payment.sslcommerz_tran_id)
        return False, 'Incomplete payment verification response.'
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

    # Verify currency (fail-closed if missing)
    currency = result.get('currency')
    if not currency or currency.upper() != 'BDT':
        logger.warning(
            'Payment currency mismatch: expected BDT, got %s for tran_id=%s',
            currency, payment.sslcommerz_tran_id,
        )
        return False, 'Invalid payment currency.'

    # Verify transaction ID matches (fail-closed if missing)
    returned_tran_id = result.get('tran_id')
    if not returned_tran_id or returned_tran_id != payment.sslcommerz_tran_id:
        logger.warning(
            'Transaction ID mismatch: expected %s, got %s',
            payment.sslcommerz_tran_id, returned_tran_id,
        )
        return False, 'Transaction ID mismatch.'

    # Verify store_id (fail-closed if missing)
    returned_store = result.get('store_id')
    if not returned_store or returned_store != settings.SSLCOMMERZ_STORE_ID:
        logger.warning(
            'Store ID mismatch: expected %s, got %s',
            settings.SSLCOMMERZ_STORE_ID, returned_store,
        )
        return False, 'Store ID mismatch.'

    return True, ''


def initiate_payment(request, amount, purpose, payment_type, reference_id=None):
    tran_id = uuid.uuid4().hex[:20]

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
        'success_url': request.build_absolute_uri(reverse('payments:success')) + f'?tran_id={tran_id}',
        'fail_url': request.build_absolute_uri(reverse('payments:fail')) + f'?tran_id={tran_id}',
        'cancel_url': request.build_absolute_uri(reverse('payments:cancel')) + f'?tran_id={tran_id}',
        'notify_url': request.build_absolute_uri(reverse('payments:notify')),
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
def payment_notify(request):
    """SSLCommerz IPN callback (server-to-server). Returns 200 OK."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    val_id = request.POST.get('val_id')
    tran_id = request.POST.get('tran_id')

    if not val_id or not tran_id:
        logger.warning('IPN missing val_id or tran_id')
        return HttpResponse('OK', status=200)

    result = verify_sslcommerz_payment(val_id)
    if result is None:
        logger.error('IPN verification unreachable for tran_id=%s', tran_id)
        return HttpResponse('OK', status=200)

    if result.get('status') != 'VALID' or not result.get('amount') or not result.get('currency'):
        logger.warning('IPN pre-validation failed for tran_id=%s', tran_id)
        return HttpResponse('OK', status=200)

    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(sslcommerz_tran_id=tran_id)

            if payment.status == 'completed':
                if not payment.user.is_membership_paid:
                    payment.user.is_membership_paid = True
                    payment.user.save(update_fields=['is_membership_paid'])
                return HttpResponse('OK', status=200)

            if payment.status != 'pending':
                logger.warning('IPN rejected non-pending payment: status=%s, tran_id=%s', payment.status, tran_id)
                return HttpResponse('OK', status=200)

            is_valid, error_msg = _validate_payment_result(result, payment)
            if not is_valid:
                logger.warning('IPN validation failed for tran_id=%s: %s', tran_id, error_msg)
                return HttpResponse('OK', status=200)

            payment.transaction_id = result.get('bank_tran_id') or None
            payment.sslcommerz_session = json.dumps(result)
            payment.save(update_fields=['transaction_id', 'sslcommerz_session', 'updated_at'])
            _complete_membership_payment(payment)

        logger.info('IPN payment completed: tran_id=%s, user=%s', tran_id, payment.user.username)
        return HttpResponse('OK', status=200)

    except Payment.DoesNotExist:
        logger.error('IPN for unknown tran_id: %s', tran_id)
        return HttpResponse('OK', status=200)


def _complete_membership_payment(payment):
    """Mark a pending payment as completed and activate the user's membership.

    Returns True if the payment was successfully completed, False otherwise.
    """
    if payment.status == 'completed':
        if not payment.user.is_membership_paid:
            payment.user.is_membership_paid = True
            payment.user.save(update_fields=['is_membership_paid'])
        membership = getattr(payment.user, 'membership', None)
        if membership and not membership.is_active:
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
        return True

    if payment.status != 'pending':
        return False

    try:
        plan = MembershipPlan.objects.get(pk=payment.reference_id)
    except (MembershipPlan.DoesNotExist, ValueError):
        logger.error('Plan %s not found for payment %s', payment.reference_id, payment.pk)
        return False
    membership, _ = Membership.objects.get_or_create(user=payment.user)
    membership.plan = plan
    membership.is_active = True
    base_time = membership.expires_at if membership.is_active and membership.expires_at and membership.expires_at > timezone.now() else timezone.now()
    membership.started_at = membership.started_at or timezone.now()
    membership.expires_at = base_time + timedelta(days=plan.duration_days)
    membership.save()

    payment.status = 'completed'
    payment.save(update_fields=['status', 'updated_at'])

    if not payment.user.is_membership_paid:
        payment.user.is_membership_paid = True
        payment.user.save(update_fields=['is_membership_paid'])

    UserActivity.objects.create(
        user=payment.user,
        activity_type='membership_purchased',
        description=f'Membership purchased for {payment.amount} BDT'
    )
    return True


@csrf_exempt
def payment_success(request):
    """SSLCommerz browser redirect after payment. Processes as fallback, then shows success page."""
    tran_id = request.POST.get('tran_id') or request.GET.get('tran_id', '')
    val_id = request.POST.get('val_id') or request.GET.get('val_id', '')

    payment_completed = False
    lookup_user = request.user if request.user.is_authenticated else None

    if tran_id and val_id:
        result = verify_sslcommerz_payment(val_id)
        if result and result.get('status') == 'VALID':
            try:
                with transaction.atomic():
                    payment = Payment.objects.select_for_update().get(sslcommerz_tran_id=tran_id)
                    is_valid, _ = _validate_payment_result(result, payment)
                    if is_valid:
                        payment.transaction_id = result.get('bank_tran_id') or None
                        payment.sslcommerz_session = json.dumps(result)
                        if payment.status == 'pending':
                            payment.save(update_fields=['transaction_id', 'sslcommerz_session', 'updated_at'])
                        else:
                            payment.save(update_fields=['transaction_id', 'sslcommerz_session'])
                        payment_completed = _complete_membership_payment(payment)
                        logger.info('Payment completed via browser redirect: tran_id=%s', tran_id)
            except (Payment.DoesNotExist, MembershipPlan.DoesNotExist) as e:
                logger.error('Browser redirect processing error: %s', e)
            except Exception as e:
                logger.error('Browser redirect unexpected error: %s', e)

    if not payment_completed and request.user.is_authenticated:
        membership = getattr(request.user, 'membership', None)
        if membership and membership.is_active:
            payment_completed = True
        else:
            completed_payment = Payment.objects.filter(
                user=request.user, payment_type='membership', status='completed'
            ).order_by('-created_at').first()
            if completed_payment:
                if not request.user.is_membership_paid:
                    request.user.is_membership_paid = True
                    request.user.save(update_fields=['is_membership_paid'])
                if membership and not membership.is_active:
                    try:
                        plan = MembershipPlan.objects.get(pk=completed_payment.reference_id)
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
                payment_completed = True

    sandbox_auto_complete = getattr(settings, 'SSLCOMMERZ_SANDBOX_AUTO_COMPLETE', False)
    if not payment_completed and settings.SSLCOMMERZ_IS_SANDBOX and sandbox_auto_complete:
        pending = None
        if tran_id:
            pending = Payment.objects.filter(
                sslcommerz_tran_id=tran_id, payment_type='membership', status='pending'
            ).select_related('user').first()
            if pending:
                lookup_user = pending.user
        elif lookup_user:
            pending = Payment.objects.filter(
                user=lookup_user, payment_type='membership', status='pending'
            ).order_by('-created_at').first()
        if pending:
            with transaction.atomic():
                pending = Payment.objects.select_for_update().get(pk=pending.pk)
                if pending.status == 'pending':
                    payment_completed = _complete_membership_payment(pending)
                    if not lookup_user.is_membership_paid:
                        lookup_user.is_membership_paid = True
                        lookup_user.save(update_fields=['is_membership_paid'])
                    logger.info('Sandbox auto-completed payment: tran_id=%s', pending.sslcommerz_tran_id)

    if payment_completed:
        effective_user = lookup_user if not request.user.is_authenticated else request.user
        membership = getattr(effective_user, 'membership', None) if effective_user else None
        payment = Payment.objects.filter(user=effective_user, status='completed').order_by('-created_at').first() if effective_user else None
        try:
            return render(request, 'membership/success.html', {
                'membership': membership,
                'payment': payment,
            })
        except Exception:
            return HttpResponse('Payment successful. You may close this page.', status=200)

    if request.user.is_authenticated:
        messages.warning(request, 'Payment verification is pending. Please check your membership status shortly.')
        return redirect('membership:pending_purchase')
    return HttpResponse('Payment verification pending. Please check your membership status later.', status=200)


@csrf_exempt
def payment_fail(request):
    """SSLCommerz fail callback. Verifies with SSLCommerz, then shows fail page."""
    if request.method not in ('POST', 'GET'):
        return HttpResponseNotAllowed(['POST', 'GET'])
    tran_id = request.POST.get('tran_id') or request.GET.get('tran_id', '')
    val_id = request.POST.get('val_id') or request.GET.get('val_id', '')
    if tran_id and val_id:
        result = verify_sslcommerz_payment(val_id)
        if result and result.get('status') == 'VALID':
            logger.warning('Fail callback received but payment is VALID: tran_id=%s', tran_id)
        elif result and result.get('status') in ('FAILED', 'CANCELLED'):
            try:
                payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
                if payment.status == 'pending':
                    payment.status = 'failed'
                    payment.save(update_fields=['status', 'updated_at'])
                    logger.info('Payment marked as failed: tran_id=%s', tran_id)
            except Payment.DoesNotExist:
                logger.warning('Fail callback for unknown tran_id: %s', tran_id)
    elif tran_id:
        try:
            payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
            if payment.status == 'pending':
                payment.status = 'failed'
                payment.save(update_fields=['status', 'updated_at'])
        except Payment.DoesNotExist:
            pass

    messages.error(request, 'Payment failed. Please try again.')
    return redirect('membership:manage')


@csrf_exempt
def payment_cancel(request):
    """SSLCommerz cancel callback. Verifies with SSLCommerz, then shows cancel page."""
    if request.method not in ('POST', 'GET'):
        return HttpResponseNotAllowed(['POST', 'GET'])
    tran_id = request.POST.get('tran_id') or request.GET.get('tran_id', '')
    val_id = request.POST.get('val_id') or request.GET.get('val_id', '')
    if tran_id and val_id:
        result = verify_sslcommerz_payment(val_id)
        if result and result.get('status') == 'VALID':
            logger.warning('Cancel callback received but payment is VALID: tran_id=%s', tran_id)
        elif result and result.get('status') in ('FAILED', 'CANCELLED'):
            try:
                payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
                if payment.status == 'pending':
                    payment.status = 'cancelled'
                    payment.save(update_fields=['status', 'updated_at'])
                    logger.info('Payment cancelled: tran_id=%s', tran_id)
            except Payment.DoesNotExist:
                logger.warning('Cancel callback for unknown tran_id: %s', tran_id)
    elif tran_id:
        try:
            payment = Payment.objects.get(sslcommerz_tran_id=tran_id)
            if payment.status == 'pending':
                payment.status = 'cancelled'
                payment.save(update_fields=['status', 'updated_at'])
        except Payment.DoesNotExist:
            pass

    messages.warning(request, 'Payment was cancelled.')
    return redirect('membership:manage')


@login_required
def download_invoice(request, payment_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    payment = get_object_or_404(Payment, pk=payment_id, user=request.user, status='completed')
    membership = getattr(request.user, 'membership', None)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=25*mm, leftMargin=25*mm, topMargin=25*mm, bottomMargin=25*mm)
    styles = getSampleStyleSheet()

    primary_color = HexColor('#4F46E5')
    success_color = HexColor('#059669')
    text_color = HexColor('#374151')
    light_gray = HexColor('#F3F4F6')

    title_style = ParagraphStyle('InvoiceTitle', parent=styles['Title'], fontSize=28, textColor=primary_color, spaceAfter=5*mm, alignment=TA_LEFT)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=HexColor('#6B7280'), alignment=TA_LEFT)
    heading_style = ParagraphStyle('Heading', parent=styles['Normal'], fontSize=12, textColor=primary_color, spaceBefore=6*mm, spaceAfter=3*mm)
    label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=9, textColor=HexColor('#6B7280'))
    value_style = ParagraphStyle('Value', parent=styles['Normal'], fontSize=11, textColor=text_color)
    value_bold = ParagraphStyle('ValueBold', parent=styles['Normal'], fontSize=11, textColor=text_color, fontName='Helvetica-Bold')
    right_style = ParagraphStyle('Right', parent=styles['Normal'], fontSize=11, textColor=text_color, alignment=TA_RIGHT)
    right_bold = ParagraphStyle('RightBold', parent=styles['Normal'], fontSize=11, textColor=text_color, alignment=TA_RIGHT, fontName='Helvetica-Bold')
    total_style = ParagraphStyle('Total', parent=styles['Normal'], fontSize=14, textColor=primary_color, alignment=TA_RIGHT, fontName='Helvetica-Bold')
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=HexColor('#9CA3AF'), alignment=TA_CENTER, spaceBefore=10*mm)

    elements = []

    header_data = [[
        Paragraph(settings.SITE_NAME, title_style),
        Paragraph('INVOICE', ParagraphStyle('InvoiceLabel', parent=styles['Normal'], fontSize=32, textColor=HexColor('#E5E7EB'), alignment=TA_RIGHT, fontName='Helvetica-Bold')),
    ]]
    header_table = Table(header_data, colWidths=[doc.width*0.6, doc.width*0.4])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 3*mm))

    elements.append(Paragraph(settings.SITE_URL, subtitle_style))
    elements.append(Spacer(1, 8*mm))

    now = timezone.now()
    info_left = [
        [Paragraph('BILL TO', label_style)],
        [Paragraph(f'{request.user.get_full_name() or request.user.username}', value_bold)],
        [Paragraph(f'{request.user.email}', value_style)],
        [Paragraph(f'{request.user.phone or "N/A"}', value_style)],
    ]
    info_right = [
        [Paragraph('INVOICE DETAILS', label_style)],
        [Paragraph(f'Invoice #: {payment.sslcommerz_tran_id or payment.transaction_id or f"INV-{payment.pk:06d}"}', value_bold)],
        [Paragraph(f'Date: {now.strftime("%B %d, %Y")}', value_style)],
        [Paragraph(f'Payment Method: SSLCommerz', value_style)],
        [Paragraph(f'Status: <font color="#059669"><b>PAID</b></font>', value_style)],
    ]

    info_table = Table([[info_left, info_right]], colWidths=[doc.width*0.5, doc.width*0.5])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10*mm))

    table_data = [
        [Paragraph('<b>Description</b>', ParagraphStyle('TH', parent=styles['Normal'], fontSize=9, textColor=HexColor('#FFFFFF'))),
         Paragraph('<b>Plan</b>', ParagraphStyle('TH', parent=styles['Normal'], fontSize=9, textColor=HexColor('#FFFFFF'), alignment=TA_CENTER)),
         Paragraph('<b>Duration</b>', ParagraphStyle('TH', parent=styles['Normal'], fontSize=9, textColor=HexColor('#FFFFFF'), alignment=TA_CENTER)),
         Paragraph('<b>Amount</b>', ParagraphStyle('TH', parent=styles['Normal'], fontSize=9, textColor=HexColor('#FFFFFF'), alignment=TA_RIGHT))],
        [Paragraph('Membership', value_style),
         Paragraph(f'{membership.plan.name if membership and membership.plan else "Annual Membership"}', ParagraphStyle('TC', parent=value_style, alignment=TA_CENTER)),
         Paragraph(f'{membership.plan.duration_days if membership and membership.plan else 365} days', ParagraphStyle('TC', parent=value_style, alignment=TA_CENTER)),
         Paragraph(f'{payment.amount} BDT', right_style)],
    ]

    items_table = Table(table_data, colWidths=[doc.width*0.35, doc.width*0.25, doc.width*0.20, doc.width*0.20])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#FFFFFF')),
        ('BACKGROUND', (0, 1), (-1, 1), HexColor('#FAFAFA')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FAFAFA'), light_gray]),
        ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 3*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3*mm),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, HexColor('#E5E7EB')),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 5*mm))

    total_data = [
        ['', '', Paragraph('Subtotal:', value_style), Paragraph(f'{payment.amount} BDT', right_style)],
        ['', '', Paragraph('Tax:', value_style), Paragraph('0.00 BDT', right_style)],
        ['', '', Paragraph('<b>TOTAL:</b>', total_style), Paragraph(f'<b>{payment.amount} BDT</b>', total_style)],
    ]
    total_table = Table(total_data, colWidths=[doc.width*0.35, doc.width*0.25, doc.width*0.20, doc.width*0.20])
    total_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 1*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1*mm),
        ('LINEABOVE', (2, 2), (-1, 2), 1, primary_color),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 15*mm))

    elements.append(Paragraph('Thank you for your payment!', ParagraphStyle('Thanks', parent=styles['Normal'], fontSize=12, textColor=success_color, alignment=TA_CENTER, fontName='Helvetica-Bold')))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph('This is a computer-generated invoice. No signature is required.', footer_style))
    elements.append(Paragraph(f'{settings.SITE_NAME} | {settings.SITE_URL}', footer_style))

    doc.build(elements)

    buffer.seek(0)
    filename = f"invoice_{payment.sslcommerz_tran_id or payment.pk}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
