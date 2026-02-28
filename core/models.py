import uuid
from django.db import models


class Submission(models.Model):
    """Stores form submission data with a unique tracking token for the confirmation link."""
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50)
    email = models.EmailField()
    address = models.TextField()
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    tracking_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.email})"


class ClickMetadata(models.Model):
    """Stores client and server metadata when user clicks the tracking link."""
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='click_metadata')
    session_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    geo_location = models.JSONField(default=dict, blank=True)
    browser = models.JSONField(default=dict, blank=True)
    device = models.JSONField(default=dict, blank=True)
    screen = models.JSONField(default=dict, blank=True)
    environment = models.JSONField(default=dict, blank=True)
    page = models.JSONField(default=dict, blank=True)
    request_headers = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Click metadata'

    def __str__(self):
        return f"Click for {self.submission.name} at {self.timestamp}"
