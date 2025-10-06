from django.contrib import admin
from .models import GAMNetwork, MCMInvitation

@admin.register(GAMNetwork)
class GAMNetworkAdmin(admin.ModelAdmin):
    list_display = [
        'network_name', 'network_code', 'network_type', 
        'status', 'currency_code', 'service_account_added', 'last_sync'
    ]
    list_filter = ['network_type', 'status', 'currency_code', 'api_version']
    search_fields = ['network_name', 'network_code', 'display_name']
    readonly_fields = ['created_at', 'updated_at', 'last_sync']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('network_code', 'network_name', 'display_name', 'network_type')
        }),
        ('Configuration', {
            'fields': ('currency_code', 'time_zone', 'status', 'api_version')
        }),
        ('Relationships', {
            'fields': ('parent_network',)
        }),
        ('Service Account', {
            'fields': ('service_account_email', 'service_account_added')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_sync'),
            'classes': ('collapse',)
        })
    )

@admin.register(MCMInvitation)
class MCMInvitationAdmin(admin.ModelAdmin):
    list_display = [
        'parent_network', 'child_network_code', 'status', 
        'invited_by', 'created_at', 'expires_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['child_network_code', 'child_network_name', 'invitation_id']
    readonly_fields = ['created_at', 'updated_at']
