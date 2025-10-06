# gam_accounts/models.py - Fixed version with AUTH_USER_MODEL

from django.db import models
from django.conf import settings
from django.utils import timezone


class GAMNetwork(models.Model):
    NETWORK_TYPE_CHOICES = [
        ('parent', 'Parent Network'),
        ('child', 'Child Network'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Pending'),
    ]
    
    network_code = models.CharField(max_length=20, unique=True)
    network_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    network_type = models.CharField(max_length=10, choices=NETWORK_TYPE_CHOICES)
    parent_network = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='child_networks')
    
    currency_code = models.CharField(max_length=3, default='USD')
    time_zone = models.CharField(max_length=50, default='UTC')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    # Service account information
    service_account_email = models.EmailField(blank=True)
    service_account_added = models.BooleanField(default=False)
    service_account_enabled = models.BooleanField(
        default=False, 
        help_text="Whether the service account/key is enabled for API access"
    )
    
    # API information
    api_version = models.CharField(max_length=20, default='v202508')
    last_sync = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.network_name} ({self.network_code}) - {self.network_type}"
    
    @property
    def is_parent(self):
        return self.network_type == 'parent'
    
    @property
    def is_child(self):
        return self.network_type == 'child'
    
    class Meta:
        verbose_name = "GAM Network"
        verbose_name_plural = "GAM Networks"

class MCMInvitation(models.Model):
    DELEGATION_CHOICES = [
        ('MANAGED_INVENTORY', 'Managed Inventory'),
        ('MANAGE_ACCOUNT', 'Manage Account'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),  # Default status, triggers sub-reports
        ('invited', 'Invited'),  # Service account/key status - can fetch main reports
        ('approved', 'Approved'), # Service account/key status - can fetch main reports
        ('not_approved', 'Not Approved'), # Rejected during verification
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
        ('awaiting_manual_send', 'Awaiting Manual Send'),
        ('api_error', 'API Error'),
        ('reject_by_child', 'Reject By Child'),
        ('withdrawn_by_parent', 'Withdrawn by Parent'),
        ('closed_policy_violation', 'Closed Policy Violation'),
        ('closed_invalid_activity', 'Closed Invalid Activity'),
    ]
    INVITE_TYPE_CHOICES = [
        ('invitation', 'Invitation'),  # sent through "Send Invite"
        ('own', 'Own'),                # added manually without API call
    ]
    USER_STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    # Core invitation fields
    parent_network = models.ForeignKey('GAMNetwork', on_delete=models.CASCADE)
    child_network_code = models.CharField(max_length=20)
    child_network_name = models.CharField(max_length=255, blank=True)
    site = models.CharField(max_length=255,blank=True, null=True, help_text="Primary site link (optional)")
    comments = models.TextField(blank=True, null=True, help_text="Internal notes or comments")
    
    # Service account status for this child network
    service_account_enabled = models.BooleanField(
        default=False, 
        help_text="Whether the service account/key is enabled for API access for this child network"
    )

    invite_type = models.CharField(
        max_length=20,
        choices=INVITE_TYPE_CHOICES,
        default='invitation',  # fallback
        help_text="Type of invite: invitation or own"
    )

    # NEW ENHANCED FIELDS for API support
    primary_contact_email = models.EmailField(blank=True, help_text="Email address where invitation will be sent")
    delegation_type = models.CharField(
        max_length=20,
        choices=DELEGATION_CHOICES,
        default='MANAGED_INVENTORY',
        help_text="Type of MCM delegation requested"
    )
    revenue_share_percentage = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Percentage parent keeps (0-100), required for MANAGE_ACCOUNT"
    )
    
    # NEW API tracking fields
    gam_company_id = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        help_text="GAM Company ID returned from createCompanies API"
    )
    api_method_used = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="Which API method succeeded (primary, alternative, manual)"
    )
    real_invitation_sent = models.BooleanField(
        default=False, 
        help_text="True if sent via GAM API, False if manual workflow"
    )
    
    # Existing fields
    invitation_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    user_status = models.CharField(
        max_length=20,
        choices=USER_STATUS_CHOICES,
        default='active',
        help_text="Admin-defined status (active/inactive)"
    )
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        method = "API" if self.real_invitation_sent else "Manual"
        revenue_info = f" ({self.revenue_share_percentage}%)" if self.revenue_share_percentage else ""
        return f"MCM ({method}): {self.parent_network.network_name} -> {self.child_network_code} ({self.delegation_type}{revenue_info})"
    
    @property
    def is_expired(self):
        """Check if invitation has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    @property
    def days_until_expiry(self):
        """Get days until expiry"""
        if self.expires_at:
            delta = self.expires_at - timezone.now()
            return max(0, delta.days)
        return None
    
    @property
    def can_fetch_main_reports(self):
        """Check if this invitation can fetch main reports"""
        return self.status in ['invited', 'approved'] and self.user_status == 'active'
    
    @property
    def should_fetch_sub_reports(self):
        """Check if this invitation should fetch sub-reports"""
        return self.status == 'pending' and self.user_status == 'active'
    
    @property
    def is_verification_rejected(self):
        """Check if this invitation was rejected during verification"""
        return self.status == 'not_approved'
    
    @property 
    def child_revenue_percentage(self):
        """Calculate child's revenue percentage"""
        if self.revenue_share_percentage:
            return 100 - self.revenue_share_percentage
        return None
    
    def mark_as_sent_via_api(self, gam_company_id, api_method='primary'):
        """Mark invitation as sent via API"""
        self.real_invitation_sent = True
        self.gam_company_id = gam_company_id
        self.api_method_used = api_method
        self.status = 'pending'
        self.save()
    
    def mark_as_manual_workflow(self):
        """Mark invitation as requiring manual sending"""
        self.real_invitation_sent = False
        self.status = 'awaiting_manual_send'
        self.save()
    
    def mark_as_accepted(self):
        """Mark invitation as accepted"""
        self.status = 'accepted'
        self.accepted_at = timezone.now()
        self.save()
    
    class Meta:
        unique_together = ['parent_network', 'child_network_code']
        verbose_name = "MCM Invitation"
        verbose_name_plural = "MCM Invitations"
        ordering = ['-created_at']
    
class AssignedPublisherChildAccount(models.Model):
    publisher = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    invitation = models.OneToOneField(MCMInvitation, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='assigned_child_accounts')
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assigned_publisher_child_accounts'

    def __str__(self):
        return f"{self.publisher.email} → {self.invitation.child_network_code} ({self.invitation.delegation_type})"