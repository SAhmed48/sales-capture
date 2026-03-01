import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit

from .forms import SubmissionForm
from .models import Submission, ClickMetadata
from .services.email import send_submission_confirmation_email
from .services.sms import send_submission_confirmation_sms

logger = logging.getLogger(__name__)

# Sensitive headers to strip when storing
SENSITIVE_HEADERS = {'authorization', 'cookie', 'x-csrftoken', 'x-api-key'}


def get_client_ip(request):
    """Extract client IP from request. Only trust proxy headers when request comes from a trusted proxy."""
    remote_addr = request.META.get('REMOTE_ADDR', '')
    trusted = getattr(settings, 'TRUSTED_PROXY_IPS', {'127.0.0.1', '::1', '172.17.0.1'})
    from_proxy = remote_addr in trusted or any(remote_addr.startswith(p.rstrip('*')) for p in trusted if '*' in p)
    if from_proxy:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()
    return remote_addr


class CustomLoginView(LoginView):
    """Custom login page for dashboard access."""
    template_name = 'core/login.html'
    redirect_authenticated_user = True


class DashboardView(LoginRequiredMixin, View):
    """Dashboard showing all submissions with their details."""
    def get(self, request):
        submissions = Submission.objects.all().prefetch_related('click_metadata')
        total_clicks = ClickMetadata.objects.count()
        week_ago = timezone.now() - timedelta(days=7)
        recent_count = Submission.objects.filter(created_at__gte=week_ago).count()
        return render(request, 'core/dashboard.html', {
            'submissions': submissions,
            'total_clicks': total_clicks,
            'recent_count': recent_count,
        })


def get_geo_from_ip(ip_address):
    """
    Fetch geo data from IP using ipinfo.io. Uses Redis cache (24h TTL) when available.
    ipinfo.io: 50k req/month free, no key, industry-standard accuracy.
    """
    if not ip_address:
        return {}
    try:
        from ipaddress import ip_address as parse_ip
        addr = parse_ip(ip_address)
        if addr.is_private or addr.is_loopback:
            return {}
    except ValueError:
        return {}
    cache_key = f'geo:{ip_address}'
    cache_ttl = 86400  # 24h - geo rarely changes per IP
    try:
        from django.core.cache import cache
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        pass
    result = {}
    try:
        import requests
        r = requests.get(
            f'https://ipinfo.io/{ip_address}/json',
            timeout=3,
            headers={'Accept': 'application/json', 'User-Agent': 'SalesCapture/1.0'}
        )
        if r.status_code == 200:
            data = r.json()
            loc = data.get('loc', '')
            lat, lon = ('', '') if not loc else (loc.split(',')[0], loc.split(',')[1]) if ',' in loc else ('', '')
            result = {
                'country': data.get('country', ''),
                'city': data.get('city', ''),
                'region': data.get('region', ''),
                'latitude': lat,
                'longitude': lon,
                'isp': data.get('org', ''),
            }
            try:
                from django.core.cache import cache
                cache.set(cache_key, result, cache_ttl)
            except Exception:
                pass
    except Exception as e:
        logger.warning("Geo lookup failed for %s: %s", ip_address, e)
    return result


def sanitize_headers(request):
    """Extract and sanitize request headers for storage."""
    headers = {}
    for key, value in request.META.items():
        if key.startswith('HTTP_'):
            header_name = key[5:].replace('_', '-').lower()
            if header_name not in SENSITIVE_HEADERS and value:
                headers[header_name] = str(value)[:500]
    return headers


@ratelimit(key='ip', rate='10/h', method='POST')
@require_http_methods(['GET', 'POST'])
def form_view(request):
    """Display and handle the submission form."""
    if request.method == 'POST':
        form = SubmissionForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            # Update existing record if same phone, else create new (email does not matter)
            submission = Submission.objects.filter(phone=data['phone']).first()
            if submission:
                for key, value in data.items():
                    setattr(submission, key, value)
                submission.save()
            else:
                submission = form.save()
            tracking_url = request.build_absolute_uri(
                reverse('core:track', args=[str(submission.tracking_token)])
            )
            email_sent = send_submission_confirmation_email(
                submission.email, tracking_url, submission.name
            )
            sms_sent = send_submission_confirmation_sms(submission.phone, tracking_url)
            if (not email_sent or not sms_sent) and settings.DEBUG:
                logger.debug("VERIFICATION LINK (credentials not configured): %s", tracking_url)
            return redirect('core:thank_you')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SubmissionForm()

    return render(request, 'core/form.html', {'form': form})


def thank_you_view(request):
    """Dedicated thank you page shown after successful submission."""
    return render(request, 'core/thank_you.html')


@ensure_csrf_cookie
def track_view(request, tracking_token):
    """Render the tracking page; JS will collect and POST metadata."""
    submission = get_object_or_404(Submission, tracking_token=tracking_token)
    return render(request, 'core/track.html', {
        'submission': submission,
        'tracking_token': tracking_token,
        'track_url': request.build_absolute_uri(reverse('core:form')),
    })


MAX_METADATA_PAYLOAD_BYTES = 20 * 1024  # 20KB


@ratelimit(key='ip', rate='20/h', method='POST')
@require_POST
def track_api_view(request, tracking_token):
    """Accept POST with client metadata, merge server data, save to DB."""
    submission = get_object_or_404(Submission, tracking_token=tracking_token)

    content_length = request.META.get('CONTENT_LENGTH')
    if content_length and int(content_length) > MAX_METADATA_PAYLOAD_BYTES:
        return JsonResponse({'error': 'Payload too large'}, status=413)

    body = request.body or b''
    if len(body) > MAX_METADATA_PAYLOAD_BYTES:
        return JsonResponse({'error': 'Payload too large'}, status=413)

    try:
        data = json.loads(body.decode('utf-8')) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    ip_address = get_client_ip(request)
    geo_location = get_geo_from_ip(ip_address) if ip_address else {}
    if settings.DEBUG and ip_address:
        logger.debug("Track API: IP=%s geo=%s", ip_address, geo_location)
    try:
        from ipaddress import ip_address as parse_ip
        stored_ip = str(parse_ip(ip_address)) if ip_address else None
    except ValueError:
        stored_ip = None

    session_id = str(uuid.uuid4())
    if request.session.session_key:
        session_id = request.session.session_key

    def safe_json(val, max_items=50):
        """Extract dict with limited keys/values to prevent abuse."""
        if not isinstance(val, dict):
            return {}
        return dict(list(val.items())[:max_items])

    meta = ClickMetadata.objects.create(
        submission=submission,
        session_id=session_id,
        ip_address=stored_ip,
        geo_location=geo_location,
        browser=safe_json(data.get('browser')),
        device=safe_json(data.get('device')),
        screen=safe_json(data.get('screen')),
        environment=safe_json(data.get('environment')),
        page=safe_json(data.get('page')),
        request_headers=sanitize_headers(request),
    )
    return JsonResponse({'ok': True, 'id': meta.pk})
