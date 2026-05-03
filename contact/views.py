import json
import threading
import os
from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
import urllib.request
import urllib.parse


def log_to_sheets(data):
    """Non-blocking write to Google Sheets — runs in background thread."""
    try:
        payload = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            settings.SHEETS_URL,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Never block the response if Sheets fails

def verify_turnstile(token, remote_ip):
    """Verify Cloudflare Turnstile token."""
    try:
        payload = urllib.parse.urlencode({
            'secret': settings.TURNSTILE_SECRET_KEY,
            'response': token,
            'remoteip': remote_ip,
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=payload,
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('success', False)
    except Exception:
        return False


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

    # ── Get client IP ────────────────────────────────────────────────
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0].strip()

    # ── Honeypot ─────────────────────────────────────────────────
    if request.POST.get('website', ''):
        return JsonResponse({'status': 'ok'})
    
    # ── Turnstile verification ───────────────────────────────────────
    turnstile_token = request.POST.get('cf-turnstile-response', '')
    if not verify_turnstile(turnstile_token, ip):
        return JsonResponse(
            {'status': 'error', 'message': 'Security check failed. Please try again.'},
            status=403
        )
    
    # ── Rate limiting ────────────────────────────────────────────────
    cache_key = f'contact_form_{ip}'
    submission_count = cache.get(cache_key, 0)

    if submission_count >= 5:
        return JsonResponse(
            {'status': 'error', 'message': 'Too many submissions. Please try again later.'},
            status=429
        )

    cache.set(cache_key, submission_count + 1, timeout=3600)  # 1 hour window

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

    # ── Send email ───────────────────────────────────────────────
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

    # ── Log to Sheets (non-blocking) ─────────────────────────────
    sheet_data = {
        'name':    name,
        'email':   email,
        'phone':   phone,
        'company': company,
        'service': service,
        'message': message,
    }
    thread = threading.Thread(target=log_to_sheets, args=(sheet_data,))
    thread.daemon = True
    thread.start()

    return JsonResponse({'status': 'ok'})