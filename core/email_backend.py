"""
Custom SMTP backend with configurable timeout to prevent worker hangs.
"""
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


class TimeoutSMTPEmailBackend(SMTPEmailBackend):
    """SMTP backend that uses EMAIL_TIMEOUT to prevent connection hangs."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("timeout", getattr(settings, "EMAIL_TIMEOUT", 10))
        super().__init__(*args, **kwargs)
