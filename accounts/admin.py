"""
Enhanced admin configuration for GAM Platform users
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Enhanced admin interface for GAM Platform users
    """
    list_display = [
        'email',
        'username', 
        'first_name',
        'last_name',
        'role_badge',
        'status_badge',
        'is_active',
        'last_login',
        'date_joined'
    ]
    list_filter = [
        'role',
        'status',
        'is_active',
        'is_staff',
        'date_joined',
        'last_login'
    ]
    search_fields = [
        'email',
        'username',
        'first_name',
        'last_name',
        'company_name'
    ]
    ordering = ['-date_joined']
    
    # Fields to show when editing a user
    fieldsets = BaseUserAdmin.fieldsets + (
        ('GAM Platform Info', {
            'fields': (
                'role',
                'phone_number',
                'company_name',
                'status',
            )
        }),
        ('Notifications', {
            'fields': (
                'email_notifications',
                'slack_notifications',
                'slack_webhook_url',
            )
        }),
        ('Tracking', {
            'fields': (
                'last_login_ip',
                'password_changed_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    # Fields to show when adding a new user
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('GAM Platform Info', {
            'fields': (
                'email',
                'first_name',
                'last_name',
                'role',
                'phone_number',
                'company_name'
            )
        }),
    )
    
    def role_badge(self, obj):
        """Display role with colored badge"""
        colors = {
            'admin': '#dc3545',    # Red
            'partner': '#28a745',  # Green
        }
        color = colors.get(obj.role, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_role_display()
        )
    role_badge.short_description = 'Role'
    
    def status_badge(self, obj):
        """Display status with colored badge"""
        colors = {
            'active': '#28a745',      # Green
            'inactive': '#6c757d',    # Gray
            'suspended': '#dc3545',   # Red
            'pending': '#ffc107',     # Yellow
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'