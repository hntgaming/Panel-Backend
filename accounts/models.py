"""
User management models - Updated for GAM Platform
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel, StatusChoices

class User(AbstractUser, TimeStampedModel):
    """
    Custom User model for GAM Platform
    Supports: Admin, Partner-Admin (publishers who connect GAM & manage sub-publishers),
    Sub-Publisher (creators/traffic partners under a partner-admin)
    """
    
    class UserRole(models.TextChoices):
        ADMIN = 'admin', 'Admin User'
        PARTNER_ADMIN = 'partner_admin', 'Partner Admin'
        SUB_PUBLISHER = 'sub_publisher', 'Sub-Publisher (Creator/Traffic Partner)'
    
    # Basic user information
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    
    # GAM Platform specific role
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PARTNER_ADMIN,
        help_text="Admin: Full access. Partner-Admin: Connects GAM & manages sub-publishers. Sub-Publisher: Creator/traffic partner."
    )
    
    # Hierarchy: sub-publishers belong to a partner-admin
    parent_publisher = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_publishers',
        limit_choices_to={'role__in': ['partner_admin', 'admin']},
        help_text="Partner-Admin who manages this sub-publisher"
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
    
    # Revenue sharing (parent network share percentage)
    revenue_share_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=10.00,
        help_text="Percentage of revenue that goes to the parent network (0-100%)"
    )
    
    # Custom fee for each partner/sub-publisher (deducted from their earnings)
    custom_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Custom fee percentage assigned by partner-admin to this sub-publisher (0-100%)"
    )
    
    # Publisher website information
    site_url = models.URLField(blank=True, help_text="Publisher's website URL")
    
    # RBAC versioning for cache invalidation
    permissions_version = models.IntegerField(default=1, help_text="Version number for permission cache invalidation")
    
    # Use email as the login field instead of username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    
    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['parent_publisher', 'role']),
            models.Index(fields=['role', 'status']),
        ]
    
    def __str__(self):
        return f"{self.email} ({self.get_full_name()})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_sites(self):
        return self.sites.all()
    
    def get_sub_publishers(self):
        return User.objects.filter(parent_publisher=self, role=self.UserRole.SUB_PUBLISHER)
    
    @property
    def is_active_user(self):
        return self.status == StatusChoices.ACTIVE and self.is_active
    
    @property
    def is_admin_user(self):
        return self.role.upper() == 'ADMIN'
    
    @property
    def is_partner_admin(self):
        return self.role == self.UserRole.PARTNER_ADMIN
    
    @property
    def is_sub_publisher(self):
        return self.role == self.UserRole.SUB_PUBLISHER
    
    def save(self, *args, **kwargs):
        if self.role == self.UserRole.ADMIN:
            self.is_staff = True
        else:
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
        ('PARTNER_ADMIN', 'Partner Admin'),
        ('SUB_PUBLISHER', 'Sub-Publisher'),
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


class PermissionAuditLog(TimeStampedModel):
    """
    Audit log for permission changes
    """
    ACTION_CHOICES = [
        ('GRANT', 'Grant Permission'),
        ('REVOKE', 'Revoke Permission'),
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
    Payment details for partner admins and sub-publishers.
    Supports both cryptocurrency and wire transfer payments.
    """
    class PaymentMethod(models.TextChoices):
        CRYPTO = 'crypto', 'Cryptocurrency (TRC20)'
        WIRE = 'wire', 'Wire Transfer'
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='payment_details',
        limit_choices_to={'role__in': ['partner_admin', 'sub_publisher']},
        help_text="Partner admin or sub-publisher user"
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
        READY = 'ready', 'Ready'
        GETTING_READY = 'getting_ready', 'Getting ready'
        REQUIRES_REVIEW = 'requires_review', 'Requires review'
        NEEDS_ATTENTION = 'needs_attention', 'Needs attention'
    
    class AdsTxtStatus(models.TextChoices):
        ADDED = 'added', 'Added'
        MISSING = 'missing', 'Missing'
    
    publisher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sites',
        limit_choices_to={'role': 'partner_admin'},
        help_text="Partner admin who owns this site"
    )
    
    url = models.URLField(
        help_text="Site URL (e.g., https://example.com)"
    )
    
    gam_status = models.CharField(
        max_length=20,
        choices=GamStatus.choices,
        default=GamStatus.GETTING_READY,
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
        default=AdsTxtStatus.MISSING,
        help_text="Status of ads.txt"
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


class TrackingAssignment(TimeStampedModel):
    """
    Assigns a subdomain to a sub-publisher for traffic attribution.
    Reports are filtered by site dimension matching the subdomain.
    """

    sub_publisher = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='tracking_assignment',
        limit_choices_to={'role': 'sub_publisher'},
        help_text="Sub-publisher this tracking is assigned to"
    )
    partner_admin = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='managed_tracking_assignments',
        limit_choices_to={'role__in': ['partner_admin', 'admin']},
        help_text="Partner-admin who created this assignment"
    )
    subdomain = models.CharField(
        max_length=255,
        help_text="Subdomain for attribution (e.g. 'creator1.example.com')"
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'accounts_tracking_assignment'
        unique_together = [['partner_admin', 'subdomain']]
        indexes = [
            models.Index(fields=['subdomain']),
            models.Index(fields=['partner_admin', 'is_active']),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.subdomain or not self.subdomain.strip():
            raise ValidationError({'subdomain': 'Subdomain is required.'})

    def __str__(self):
        return f"{self.sub_publisher.email} -> {self.subdomain}"


class Subdomain(TimeStampedModel):
    """
    Subdomains created by partner-admins for traffic routing.
    """
    partner_admin = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='subdomains',
        limit_choices_to={'role__in': ['partner_admin', 'admin']},
        help_text="Partner-admin who owns this subdomain"
    )
    subdomain = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Subdomain prefix (e.g. 'creator1' for creator1.publisher.com)"
    )
    base_domain = models.CharField(
        max_length=255,
        help_text="Base domain (e.g. 'publisher.com')"
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_subdomain',
        limit_choices_to={'role': 'sub_publisher'},
        help_text="Sub-publisher assigned to this subdomain"
    )
    is_active = models.BooleanField(default=True)
    dns_verified = models.BooleanField(
        default=False,
        help_text="Whether DNS for this subdomain has been verified"
    )

    class Meta:
        db_table = 'accounts_subdomain'
        indexes = [
            models.Index(fields=['partner_admin', 'is_active']),
        ]

    def __str__(self):
        return f"{self.subdomain}.{self.base_domain}"

    @property
    def full_domain(self):
        return f"{self.subdomain}.{self.base_domain}"


class Tutorial(TimeStampedModel):
    """
    Platform tutorials accessible to all users.
    Explains how the platform works and how to interpret data.
    """

    class Category(models.TextChoices):
        GETTING_STARTED = 'getting_started', 'Getting Started'
        TRACKING = 'tracking', 'Tracking & Attribution'
        EARNINGS = 'earnings', 'Earnings & Payments'
        REPORTS = 'reports', 'Reports & Analytics'
        GAM_SETUP = 'gam_setup', 'GAM Setup'
        SUBDOMAINS = 'subdomains', 'Subdomain Configuration'
        FAQ = 'faq', 'FAQ'

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.GETTING_STARTED
    )
    content = models.TextField(help_text="Tutorial content in Markdown format")
    summary = models.CharField(max_length=500, blank=True)
    order = models.IntegerField(default=0, help_text="Display order within category")
    is_published = models.BooleanField(default=True)
    target_roles = models.JSONField(
        default=list,
        help_text="List of roles this tutorial is visible to (empty = all roles)"
    )
    video_url = models.URLField(blank=True, help_text="Optional video tutorial URL")

    class Meta:
        db_table = 'accounts_tutorial'
        ordering = ['category', 'order', 'title']
        indexes = [
            models.Index(fields=['category', 'is_published']),
        ]

    def __str__(self):
        return f"[{self.category}] {self.title}"


class GAMCredential(TimeStampedModel):
    """
    Per-partner GAM connection credentials.
    Service Account: Partner adds our service email as admin in their GAM network.
    OAuth 2.0: Partner authenticates via Google OAuth consent flow.
    """

    class AuthMethod(models.TextChoices):
        SERVICE_ACCOUNT = 'service_account', 'Shared Service Account'
        OAUTH2 = 'oauth2', 'OAuth 2.0'

    partner_admin = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='gam_credential',
        limit_choices_to={'role': 'partner_admin'},
    )
    auth_method = models.CharField(
        max_length=20,
        choices=AuthMethod.choices,
        default=AuthMethod.SERVICE_ACCOUNT,
    )
    network_code = models.CharField(
        max_length=50,
        help_text="Partner's GAM network code",
    )

    oauth_refresh_token = models.TextField(
        blank=True,
        help_text="Encrypted OAuth 2.0 refresh token",
    )
    oauth_client_id = models.CharField(
        max_length=255,
        blank=True,
    )

    is_connected = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    connection_error = models.TextField(blank=True)

    class Meta:
        db_table = 'accounts_gam_credential'
        verbose_name = 'GAM Credential'
        verbose_name_plural = 'GAM Credentials'

    def __str__(self):
        return f"{self.partner_admin.email} - {self.get_auth_method_display()} ({self.network_code})"

    @property
    def service_account_email(self):
        return getattr(settings, 'GAM_SERVICE_ACCOUNT_EMAIL', '')
