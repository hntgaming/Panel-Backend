"""
User management models - Updated for GAM Platform
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from core.models import TimeStampedModel, StatusChoices
# Removed gam_accounts dependencies

class User(AbstractUser, TimeStampedModel):
    """
    Custom User model for GAM Platform
    Enhanced with role-based access control
    """
    
    class UserRole(models.TextChoices):
        ADMIN = 'admin', 'Admin User'
        PUBLISHER = 'publisher', 'Publisher User'
    
    # Basic user information
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    
    # GAM Platform specific role
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PUBLISHER,
        help_text="Admin: Full access. Publisher: Permission-based."
    )
    
    # User status
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE
    )
    
    # Profile information
    phone_number = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=100, blank=True)
    
    # User preferences
    email_notifications = models.BooleanField(default=True)
    slack_notifications = models.BooleanField(default=False)
    slack_webhook_url = models.URLField(blank=True, help_text="Slack webhook for notifications")
    
    # Account management
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    
    # Revenue sharing
    revenue_share_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=10.00,
        help_text="Percentage of revenue that goes to the parent network (0-100%)"
    )
    
    # Publisher website information
    site_url = models.URLField(blank=True, help_text="Publisher's website URL")
    network_id = models.CharField(max_length=50, blank=True, help_text="Publisher's GAM network ID")
    
    # RBAC versioning for cache invalidation
    permissions_version = models.IntegerField(default=1, help_text="Version number for permission cache invalidation")
    
    # Use email as the login field instead of username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    
    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.email} ({self.get_full_name()})"
    
    def get_full_name(self):
        """Return the full name of the user"""
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_sites(self):
        """Get all sites for this publisher"""
        return self.sites.all()
    
    @property
    def is_active_user(self):
        """Check if user is active"""
        return self.status == StatusChoices.ACTIVE and self.is_active
    
    @property
    def is_admin_user(self):
        """Check if user is admin"""
        return self.role.upper() == 'ADMIN'
    
    @property
    def is_publisher_user(self):
        """Check if user is publisher"""
        return self.role.upper() == 'PUBLISHER'
    
    def save(self, *args, **kwargs):
        """Override save to handle role-based staff status"""
        # Admin users should be staff to access Django admin
        if self.role == self.UserRole.ADMIN:
            self.is_staff = True
        elif self.role == self.UserRole.PUBLISHER:
            self.is_staff = False
        
        super().save(*args, **kwargs)


class PublisherPermission(models.Model):
    class PermissionChoices(models.TextChoices):
        MANAGE_PUBLISHERS = 'manage_publishers', 'Manage Publishers'
        SETTINGS = 'settings', 'Settings'
        MANAGED_ACCOUNTS = 'managed_accounts', 'Managed Accounts'
        REPORTS = 'reports', 'Reports'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='publisher_permissions', null=True, blank=True)
    permission = models.CharField(max_length=50, choices=PermissionChoices.choices)

    class Meta:
        db_table = 'accounts_publisher_permission'


# RBAC Models
class Permission(TimeStampedModel):
    """
    Canonical permissions catalog
    """
    key = models.CharField(
        max_length=100,
        unique=True,
        help_text="Permission key (e.g., 'reports.view')"
    )
    description = models.TextField(
        help_text="Human-readable description of the permission"
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="Permission category for organization"
    )
    
    class Meta:
        db_table = 'rbac_permissions'
        ordering = ['category', 'key']
    
    def __str__(self):
        return f"{self.key} - {self.description}"


class RolePermission(TimeStampedModel):
    """
    Default permissions per role
    """
    ROLE_CHOICES = [
        ('ADMIN', 'Admin User'),
        ('PARENT', 'Parent Network User'),
        ('PUBLISHER', 'Publisher User'),
    ]
    
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        help_text="User role"
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='role_permissions',
        null=True,
        blank=True
    )
    
    class Meta:
        db_table = 'rbac_role_permissions'
        unique_together = ['role', 'permission']
        ordering = ['role', 'permission__key']
    
    def __str__(self):
        return f"{self.role} -> {self.permission.key}"


class UserPermissionOverride(TimeStampedModel):
    """
    Per-user permission overrides (mainly for Partners)
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='permission_overrides',
        null=True,
        blank=True
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='user_overrides',
        null=True,
        blank=True
    )
    allowed = models.BooleanField(
        help_text="True to grant permission, False to deny"
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='granted_overrides',
        help_text="User who granted/revoked this override"
    )
    reason = models.TextField(
        blank=True,
        help_text="Reason for this override"
    )
    
    class Meta:
        db_table = 'rbac_user_permission_overrides'
        unique_together = ['user', 'permission']
        ordering = ['user__email', 'permission__key']
    
    def __str__(self):
        action = "GRANT" if self.allowed else "DENY"
        return f"{self.user.email} -> {action} {self.permission.key}"


class PublisherAccountAccess(TimeStampedModel):
    """
    Publisher to Account assignments for managed inventory
    """
    publisher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='assigned_accounts',
        limit_choices_to={'role': 'PUBLISHER'},
        null=True,
        blank=True
    )
    # Removed MCM invitation dependency - simplified for managed inventory
    child_network_code = models.CharField(
        max_length=20,
        default='',
        help_text="Child network code for managed inventory"
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='granted_account_access',
        help_text="Admin who granted this access"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this assignment"
    )
    
    class Meta:
        db_table = 'rbac_publisher_account_access'
        unique_together = ['publisher', 'child_network_code']
        ordering = ['publisher__email', 'child_network_code']
    
    def __str__(self):
        return f"{self.publisher.email} -> {self.child_network_code}"


class ParentNetwork(TimeStampedModel):
    """
    Parent network assignments for PARENT users
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='parent_network_assignment',
        limit_choices_to={'role': 'PARENT'},
        null=True,
        blank=True
    )
    # Removed parent network dependency - simplified for managed inventory
    parent_network_code = models.CharField(
        max_length=20,
        default='',
        help_text="Parent network code for managed inventory"
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='granted_parent_networks',
        help_text="Admin who granted this access"
    )
    
    class Meta:
        db_table = 'rbac_parent_networks'
        ordering = ['user__email']
    
    def __str__(self):
        return f"{self.user.email} -> {self.parent_network_code}"


class PermissionAuditLog(TimeStampedModel):
    """
    Audit log for permission changes
    """
    ACTION_CHOICES = [
        ('GRANT', 'Grant Permission'),
        ('REVOKE', 'Revoke Permission'),
        ('ASSIGN_ACCOUNT', 'Assign Account'),
        ('UNASSIGN_ACCOUNT', 'Unassign Account'),
        ('ASSIGN_PARENT', 'Assign Parent Network'),
        ('UNASSIGN_PARENT', 'Unassign Parent Network'),
    ]
    
    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='permission_audit_logs',
        null=True,
        blank=True
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    # Removed gam_accounts dependencies - simplified for managed inventory
    child_network_code = models.CharField(
        max_length=20,
        default='',
        help_text="Child network code for managed inventory"
    )
    parent_network_code = models.CharField(
        max_length=20,
        default='',
        help_text="Parent network code for managed inventory"
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='performed_permission_actions'
    )
    reason = models.TextField(
        blank=True,
        help_text="Reason for the action"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user who performed the action"
    )
    
    class Meta:
        db_table = 'rbac_permission_audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['target_user', '-created_at']),
            models.Index(fields=['performed_by', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} for {self.target_user.email} by {self.performed_by.email if self.performed_by else 'System'}"


class PaymentDetail(TimeStampedModel):
    """
    Payment details for publishers
    Supports both cryptocurrency and wire transfer payments
    """
    class PaymentMethod(models.TextChoices):
        CRYPTO = 'crypto', 'Cryptocurrency (TRC20)'
        WIRE = 'wire', 'Wire Transfer'
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='payment_details',
        limit_choices_to={'role': 'publisher'},
        help_text="Publisher user"
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        help_text="Preferred payment method"
    )
    
    # Cryptocurrency fields (TRC20)
    crypto_wallet_address = models.CharField(
        max_length=255,
        blank=True,
        help_text="TRC20 wallet address for crypto payments"
    )
    
    # Wire transfer fields
    beneficiary_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Beneficiary name for wire transfer"
    )
    bank_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Bank name"
    )
    iban = models.CharField(
        max_length=50,
        blank=True,
        help_text="IBAN (International Bank Account Number)"
    )
    swift_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="SWIFT/BIC code"
    )
    country = models.CharField(
        max_length=100,
        blank=True,
        help_text="Bank country"
    )
    
    # Additional fields
    notes = models.TextField(
        blank=True,
        help_text="Additional payment notes or instructions"
    )
    
    class Meta:
        db_table = 'accounts_payment_details'
        verbose_name = 'Payment Detail'
        verbose_name_plural = 'Payment Details'
    
    def __str__(self):
        return f"{self.user.email} - {self.get_payment_method_display()}"
    
    def clean(self):
        """Validate payment details based on payment method"""
        from django.core.exceptions import ValidationError
        
        if self.payment_method == self.PaymentMethod.CRYPTO:
            if not self.crypto_wallet_address:
                raise ValidationError({
                    'crypto_wallet_address': 'Wallet address is required for crypto payments'
                })
        elif self.payment_method == self.PaymentMethod.WIRE:
            required_fields = {
                'beneficiary_name': self.beneficiary_name,
                'bank_name': self.bank_name,
                'iban': self.iban,
                'swift_code': self.swift_code,
                'country': self.country,
            }
            missing_fields = [name for name, value in required_fields.items() if not value]
            if missing_fields:
                raise ValidationError({
                    field: f'{field.replace("_", " ").title()} is required for wire transfer'
                    for field in missing_fields
                })


class Site(TimeStampedModel):
    """
    Site model to track publisher sites with GAM and ads.txt status
    """
    class GamStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ADDED = 'added', 'Added to GAM'
        FAILED = 'failed', 'Failed to Add'
        NOT_ADDED = 'not_added', 'Not Added'
    
    class AdsTxtStatus(models.TextChoices):
        NOT_VERIFIED = 'not_verified', 'Not Verified'
        VERIFIED = 'verified', 'Verified'
        INVALID = 'invalid', 'Invalid'
        PENDING = 'pending', 'Pending Verification'
    
    publisher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sites',
        limit_choices_to={'role': 'publisher'},
        help_text="Publisher who owns this site"
    )
    
    url = models.URLField(
        help_text="Site URL (e.g., https://example.com)"
    )
    
    gam_status = models.CharField(
        max_length=20,
        choices=GamStatus.choices,
        default=GamStatus.NOT_ADDED,
        help_text="Status of site in GAM"
    )
    
    gam_site_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="GAM Site ID if added to GAM"
    )
    
    ads_txt_status = models.CharField(
        max_length=20,
        choices=AdsTxtStatus.choices,
        default=AdsTxtStatus.NOT_VERIFIED,
        help_text="Status of ads.txt verification"
    )
    
    ads_txt_last_checked = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time ads.txt was checked"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about the site"
    )
    
    class Meta:
        db_table = 'accounts_site'
        verbose_name = 'Site'
        verbose_name_plural = 'Sites'
        unique_together = [['publisher', 'url']]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.url} ({self.publisher.email})"
