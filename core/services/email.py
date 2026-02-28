import logging
from pathlib import Path

from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"


def send_submission_confirmation_email(to_email: str, tracking_url: str, recipient_name: str) -> bool:
    """Send confirmation email with tracking link."""
    if not all([getattr(settings, 'EMAIL_HOST_USER', ''), getattr(settings, 'EMAIL_HOST_PASSWORD', '')]):
        logger.warning("Email credentials not configured. Skipping confirmation email.")
        return False

    subject = "Thank you for submitting your information"
    template_path = TEMPLATE_DIR / "submission_confirmation.txt"
    try:
        message = template_path.read_text().format(
            recipient_name=recipient_name,
            tracking_url=tracking_url,
        )
    except FileNotFoundError:
        logger.warning("Email template not found at %s, using fallback", template_path)
        message = f"Dear {recipient_name},\n\nThank you for submitting your information.\n\nVerify: {tracking_url}\n\nBest regards,\nThe Team"
    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=True,
        )
        if sent == 0:
            logger.warning("Failed to send confirmation email to %s (check credentials)", to_email)
        return sent > 0
    except Exception as e:
        logger.warning("Failed to send confirmation email to %s: %s", to_email, e)
        return False
