from django.contrib import admin
from .models import Submission, ClickMetadata


class ClickMetadataInline(admin.TabularInline):
    model = ClickMetadata
    extra = 0
    readonly_fields = ('session_id', 'ip_address', 'timestamp', 'browser', 'device', 'screen')


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'city', 'country', 'created_at', 'updated_at')
    list_filter = ('country', 'created_at')
    search_fields = ('name', 'email', 'phone')
    readonly_fields = ('tracking_token', 'created_at', 'updated_at')
    inlines = [ClickMetadataInline]


@admin.register(ClickMetadata)
class ClickMetadataAdmin(admin.ModelAdmin):
    list_display = ('submission_with_phone', 'ip_address', 'timestamp')

    @admin.display(description='Submission')
    def submission_with_phone(self, obj):
        return f"{obj.submission.name} ({obj.submission.phone})"
    list_filter = ('timestamp',)
    readonly_fields = ('submission', 'session_id', 'ip_address', 'geo_location', 'browser',
                      'device', 'screen', 'environment', 'page', 'request_headers', 'timestamp')
