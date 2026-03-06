import json
import logging
import re
import uuid
from datetime import timedelta, datetime

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit

from .forms import SubmissionForm
from .models import Submission, ClickMetadata
from .pdf_export import build_submissions_pdf
from .services.email import send_submission_confirmation_email
from .services.sms import send_submission_confirmation_sms

logger = logging.getLogger(__name__)

# Sensitive headers to strip when storing
SENSITIVE_HEADERS = {'authorization', 'cookie', 'x-csrftoken', 'x-api-key'}


def get_client_ip(request):
    """Extract client IP from request. Only trust proxy headers when request comes from a trusted proxy."""
    remote_addr = request.META.get('REMOTE_ADDR', '')
    trusted = getattr(settings, 'TRUSTED_PROXY_IPS', {'127.0.0.1', '::1', '172.17.0.1'})

    def is_trusted(addr, entry):
        entry = entry.strip()
        if '/' in entry:
            try:
                from ipaddress import ip_address, ip_network
                return ip_address(addr) in ip_network(entry)
            except ValueError:
                return False
        if '*' in entry:
            return addr.startswith(entry.rstrip('*'))
        return addr == entry

    from_proxy = any(is_trusted(remote_addr, p) for p in trusted)
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


def _get_submissions_queryset(request):
    """Build submissions queryset with optional date filter and search (name, phone). Same logic for dashboard and PDF export."""
    qs = Submission.objects.all().order_by('-created_at')
    filter_days = request.GET.get('days', '').strip()
    filter_period = request.GET.get('period', '').strip()
    filter_from = request.GET.get('from', '').strip()
    filter_to = request.GET.get('to', '').strip()
    search = request.GET.get('search', '').strip()

    if filter_period == 'today':
        today = timezone.now().date()
        qs = qs.filter(created_at__date=today)
    elif filter_period == 'yesterday':
        yesterday = (timezone.now() - timedelta(days=1)).date()
        qs = qs.filter(created_at__date=yesterday)
    elif filter_days:
        try:
            n = int(filter_days)
            if n > 0:
                since = timezone.now() - timedelta(days=n)
                qs = qs.filter(created_at__gte=since)
        except ValueError:
            pass
    elif filter_from or filter_to:
        try:
            if filter_from:
                from_date = datetime.strptime(filter_from, '%Y-%m-%d').date()
                qs = qs.filter(created_at__date__gte=from_date)
            if filter_to:
                to_date = datetime.strptime(filter_to, '%Y-%m-%d').date()
                qs = qs.filter(created_at__date__lte=to_date)
        except ValueError:
            pass

    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))

    return qs.prefetch_related('click_metadata'), filter_days, filter_period, filter_from, filter_to, search


PAGE_SIZE_OPTIONS = [10, 15, 25, 50]
DASHBOARD_PAGE_SIZE_DEFAULT = 15


def _page_numbers_to_display(current, total, max_visible=7):
    """Return list of (page_num, is_ellipsis) for pagination links. Ellipsis entries are (None, True)."""
    if total <= max_visible:
        return [(p, False) for p in range(1, total + 1)]
    result = []
    shown = set()
    # Always show first
    result.append((1, False))
    shown.add(1)
    # Pages around current
    for p in range(max(1, current - 2), min(total + 1, current + 3)):
        if p not in shown:
            result.append((p, False))
            shown.add(p)
    # Always show last
    if total not in shown:
        result.append((total, False))
        shown.add(total)
    # Sort and insert ellipsis where there are gaps
    result.sort(key=lambda x: (x[0] or 0))
    out = []
    prev = 0
    for p, is_el in result:
        if prev and p - prev > 1:
            out.append((None, True))
        out.append((p, False))
        prev = p
    return out


class DashboardView(LoginRequiredMixin, View):
    """Dashboard showing all submissions with their details. Supports date filter, search, and pagination."""
    def get(self, request):
        submissions_qs, filter_days, filter_period, filter_from, filter_to, search = _get_submissions_queryset(request)

        try:
            per_page = int(request.GET.get('per_page', DASHBOARD_PAGE_SIZE_DEFAULT))
            if per_page not in PAGE_SIZE_OPTIONS:
                per_page = DASHBOARD_PAGE_SIZE_DEFAULT
        except (ValueError, TypeError):
            per_page = DASHBOARD_PAGE_SIZE_DEFAULT

        paginator = Paginator(submissions_qs, per_page)
        page_number = request.GET.get('page', 1)
        page = paginator.get_page(page_number)
        total_clicks = ClickMetadata.objects.count()
        week_ago = timezone.now() - timedelta(days=7)
        recent_count = Submission.objects.filter(created_at__gte=week_ago).count()
        get_copy = request.GET.copy()
        for key in ('page',):
            if key in get_copy:
                get_copy.pop(key)
        pagination_query = get_copy.urlencode()

        page_numbers = _page_numbers_to_display(page.number, paginator.num_pages) if paginator.num_pages > 1 else []

        return render(request, 'core/dashboard.html', {
            'page': page,
            'submissions': page.object_list,
            'total_clicks': total_clicks,
            'recent_count': recent_count,
            'filter_days': filter_days,
            'filter_period': filter_period,
            'filter_from': filter_from,
            'filter_to': filter_to,
            'search': search,
            'pagination_query': pagination_query,
            'per_page': per_page,
            'page_size_options': PAGE_SIZE_OPTIONS,
            'page_numbers': page_numbers,
        })


PDF_EXPORT_MAX_SUBMISSIONS = 200


class ExportSubmissionPdfView(LoginRequiredMixin, View):
    """Export a single submission with its click history as PDF."""
    def get(self, request, pk):
        submission = Submission.objects.filter(pk=pk).prefetch_related('click_metadata').first()
        if not submission:
            raise Http404("Submission not found")
        pdf_bytes = build_submissions_pdf([submission])
        name_slug = re.sub(r'[^\w\s-]', '', submission.name).strip()[:50].replace(' ', '-') or 'submission'
        filename = f"submission-{pk}-{name_slug}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ExportSubmissionsPdfView(LoginRequiredMixin, View):
    """Export submissions as PDF. Respects same date filter and search as dashboard."""
    def get(self, request):
        submissions_qs, _fd, _fp, _ff, _ft, _search = _get_submissions_queryset(request)
        submissions = list(submissions_qs[:PDF_EXPORT_MAX_SUBMISSIONS])
        if not submissions:
            response = HttpResponse(b'', content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="submissions-export-empty.pdf"'
            return response
        pdf_bytes = build_submissions_pdf(submissions)
        date_str = timezone.now().strftime('%Y-%m-%d')
        filename = f"submissions-export-{date_str}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class DeleteSubmissionView(LoginRequiredMixin, View):
    """Delete a submission and its click metadata. Accepts POST or DELETE. Returns JSON for API, redirects for form."""
    def post(self, request, pk):
        return self._delete(request, pk)

    def delete(self, request, pk):
        return self._delete(request, pk)

    def _delete(self, request, pk):
        submission = get_object_or_404(Submission, pk=pk)
        submission.delete()
        if request.accepts('text/html'):
            messages.success(request, f'Submission "{submission.name}" has been deleted.')
            return redirect(reverse('core:dashboard') + '?' + request.GET.urlencode())
        return JsonResponse({'deleted': True, 'id': pk})


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


@login_required
@ratelimit(key='ip', rate='10/h', method='POST')
@require_http_methods(['GET', 'POST'])
def form_view(request):
    """Display and handle the submission form."""
    if request.method == 'POST':
        form = SubmissionForm(request.POST)
        if form.is_valid():
            # Always create new submission (never update existing)
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
    """Dedicated thank you page shown after successful submission or link verification."""
    verified = request.GET.get('verified') == '1'
    return render(request, 'core/thank_you.html', {'verified': verified})


def favicon_view(request):
    """Return 204 No Content for /favicon.ico to avoid 404 log noise."""
    return HttpResponse(status=204)


@ensure_csrf_cookie
def track_view(request, tracking_token):
    """Render the tracking page; JS will collect and POST metadata."""
    submission = get_object_or_404(Submission, tracking_token=tracking_token)
    return render(request, 'core/track.html', {
        'submission': submission,
        'tracking_token': tracking_token,
        'track_url': request.build_absolute_uri(reverse('core:thank_you')) + '?verified=1',
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
