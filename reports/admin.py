from django.contrib import admin
from .models import MasterMetaData, ReportSyncLog
@admin.register(MasterMetaData)
class MasterMetaDataAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'child_network_code', 'dimension_type', 'dimension_value',
        'impressions', 'revenue', 'ecpm', 'publisher_id'
    ]
    list_filter = [
        'dimension_type', 'date', 'parent_network_code', 
        'created_at', 'updated_at'
    ]
    search_fields = [
        'child_network_code', 'dimension_value', 
        'parent_network_code'
    ]
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Source Information', {
            'fields': ('parent_network_code', 'child_network_code', 'publisher_id')
        }),
        ('Dimension Data', {
            'fields': ('date', 'dimension_type', 'dimension_value')
        }),
        ('Metrics', {
            'fields': (
                'impressions', 'revenue', 'ecpm', 'clicks', 'ctr',
                'eligible_ad_requests', 'viewable_impressions_rate', 'total_ad_requests'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
@admin.register(ReportSyncLog)
class ReportSyncLogAdmin(admin.ModelAdmin):
    list_display = [
        'sync_id', 'status', 'date_from', 'date_to',
        'successful_networks', 'failed_networks', 'duration_seconds',
        'triggered_by', 'is_manual', 'started_at'
    ]
    list_filter = ['status', 'is_manual', 'started_at']
    search_fields = ['sync_id', 'triggered_by__email']
    readonly_fields = [
        'sync_id', 'started_at', 'completed_at', 'duration_seconds',
        'total_networks_processed', 'successful_networks', 'failed_networks',
        'total_records_created', 'total_records_updated'
    ]
    fieldsets = (
        ('Sync Information', {
            'fields': ('sync_id', 'status', 'date_from', 'date_to', 'triggered_by', 'is_manual')
        }),
        ('Execution Details', {
            'fields': (
                'started_at', 'completed_at', 'duration_seconds',
                'total_networks_processed', 'successful_networks', 'failed_networks'
            )
        }),
        ('Results', {
            'fields': ('total_records_created', 'total_records_updated')
        }),
        ('Errors', {
            'fields': ('error_message', 'network_errors'),
            'classes': ('collapse',)
        })
    )