import os
from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_POST
def submit(request):
    # ── Extract fields ───────────────────────────────────────────
    name    = request.POST.get('name',    '').strip()
    email   = request.POST.get('email',   '').strip()
    phone   = request.POST.get('phone',   '').strip()
    company = request.POST.get('company', '').strip()
    service = request.POST.get('service', '').strip()
    message = request.POST.get('message', '').strip()

    # ── Honeypot — bots fill this, humans don't ──────────────────
    if request.POST.get('website', ''):
        return JsonResponse({'status': 'ok'})  # silent discard

    # ── Validation ───────────────────────────────────────────────
    errors = {}
    if not name:
        errors['name'] = 'Name is required.'
    if not email or '@' not in email:
        errors['email'] = 'A valid email address is required.'
    if not message:
        errors['message'] = 'Message is required.'

    if errors:
        return JsonResponse({'status': 'error', 'errors': errors}, status=400)

    # ── Build email body ─────────────────────────────────────────
    subject = f"New Enquiry: {service or 'General'} — {name}"
    body = "\n".join([
        "New enquiry from arglobalservices.co.uk",
        "",
        "─────────────────────────────────",
        f"Name:    {name}",
        f"Email:   {email}",
        f"Phone:   {phone   or 'Not provided'}",
        f"Company: {company or 'Not provided'}",
        f"Service: {service or 'Not specified'}",
        "─────────────────────────────────",
        "",
        "Message:",
        message,
        "",
        f"Reply directly to: {email}",
    ])

    # ── Send ─────────────────────────────────────────────────────
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[settings.RECIPIENT_EMAIL],
            fail_silently=False,
        )
    except Exception as e:
        return JsonResponse(
            {'status': 'error', 'message': 'Failed to send email.'},
            status=500
        )

    return JsonResponse({'status': 'ok'})