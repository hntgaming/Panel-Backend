"""
User management models - Updated for GAM Platform
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from core.models import TimeStampedModel, StatusChoices
from gam_accounts.models import GAMNetwork

class User(AbstractUser, TimeStampedModel):
    """
    Custom User model for GAM Platform
    Enhanced with role-based access control
    """
    
    class UserRole(models.TextChoices):
        ADMIN = 'admin', 'Admin User'
        PUBLISHER = 'publisher', 'Publisher User'
        PARENT = 'parent', 'Parent Network User'
    
    # Basic user information
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    
    # GAM Platform specific role
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PUBLISHER,
        help_text="Admin: Full access. Publisher: Permission-based. Parent: Network-scoped access."
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
    
    @property
    def is_parent_user(self):
        """Check if user is parent network user"""
        return self.role.upper() == 'PARENT'
    
    def save(self, *args, **kwargs):
        """Override save to handle role-based staff status"""
        # Admin users should be staff to access Django admin
        if self.role == self.UserRole.ADMIN:
            self.is_staff = True
        elif self.role in [self.UserRole.PUBLISHER, self.UserRole.PARENT]:
            self.is_staff = False
        
        super().save(*args, **kwargs)


class PublisherPermission(models.Model):
    class PermissionChoices(models.TextChoices):
        MANAGE_PUBLISHERS = 'manage_publishers', 'Manage Publishers'
        SETTINGS = 'settings', 'Settings'
        MANAGED_ACCOUNTS = 'managed_accounts', 'Managed Accounts'
        REPORTS = 'reports', 'Reports'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='publisher_permissions')
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
        related_name='role_permissions'
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
        related_name='permission_overrides'
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='user_overrides'
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
        limit_choices_to={'role': 'PUBLISHER'}
    )
    account = models.ForeignKey(
        'gam_accounts.MCMInvitation',
        on_delete=models.CASCADE,
        related_name='assigned_publishers'
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
        unique_together = ['publisher', 'account']
        ordering = ['publisher__email', 'account__child_network_name']
    
    def __str__(self):
        return f"{self.publisher.email} -> {self.account.child_network_name}"


class ParentNetwork(TimeStampedModel):
    """
    Parent network assignments for PARENT users
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='parent_network_assignment',
        limit_choices_to={'role': 'PARENT'}
    )
    parent_network = models.ForeignKey(
        'gam_accounts.GAMNetwork',
        on_delete=models.CASCADE,
        related_name='parent_users'
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
        return f"{self.user.email} -> {self.parent_network.network_name}"


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
        related_name='permission_audit_logs'
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    account = models.ForeignKey(
        'gam_accounts.MCMInvitation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='permission_audit_logs'
    )
    parent_network = models.ForeignKey(
        'gam_accounts.GAMNetwork',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='permission_audit_logs'
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
