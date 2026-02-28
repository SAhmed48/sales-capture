import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def send_submission_confirmation_sms(to_phone: str, tracking_url: str) -> bool:
    """Send confirmation SMS with tracking link via Twilio."""
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM_NUMBER]):
        logger.warning("Twilio credentials not configured. Skipping SMS.")
        return False
    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message_body = (
            "Thanks for your submission! Please confirm the link below to complete the final step: "
            f"{tracking_url}"
        )
        client.messages.create(
            body=message_body,
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_phone,
        )
        return True
    except TwilioRestException as e:
        if e.status == 401:
            logger.warning("Twilio credentials invalid. Skipping SMS.")
        else:
            logger.warning("Failed to send confirmation SMS to %s: %s", to_phone, e)
        return False
    except Exception as e:
        logger.warning("Failed to send confirmation SMS to %s: %s", to_phone, e)
        return False
