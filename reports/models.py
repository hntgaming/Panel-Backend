# reports/models.py - FIXED with Currency Field

from django.db import models
from django.utils import timezone
from django.conf import settings
from gam_accounts.models import MCMInvitation, GAMNetwork

DIMENSION_CHOICES = [
    ('overview', 'Overview'),
    ('site', 'App / Site'),  # Corrected: appSite -> site
    ('trafficSource', 'Traffic Source'),
    ('deviceCategory', 'Device Category'),
    ('country', 'Country'),
    ('carrier', 'Carrier / ISP'),
    ('browser', 'Browser'),
    ('country_carrier', 'Country + Carrier'),  # Added for geo-spoofing detection
]

class MasterMetaData(models.Model):
    """
    Unified reporting table for GAM analytics
    Optimized with proper indexing and validation
    """
    # Source relationships
    parent_network = models.ForeignKey(
        GAMNetwork,
        on_delete=models.CASCADE,
        help_text="Parent GAM network that fetched this data",
        db_index=True
    )
    invitation = models.ForeignKey(
        MCMInvitation,
        on_delete=models.CASCADE,
        help_text="MCM invitation linking parent to child",
        db_index=True
    )

    # Denormalized fields for fast filtering
    child_network_code = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Child network code for direct filtering"
    )
    publisher_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Publisher assigned to this child network"
    )

    # Dimension + Date for flexible reporting
    dimension_type = models.CharField(
        max_length=32, 
        choices=DIMENSION_CHOICES, 
        db_index=True,
        help_text="Type of dimension breakdown"
    )
    dimension_value = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        help_text="Specific value for the dimension (e.g., 'United States' for country)"
    )
    date = models.DateField(
        default=timezone.now, 
        db_index=True,
        help_text="Date of the report data"
    )

    # 🆕 Currency tracking (THIS WAS MISSING!)
    currency = models.CharField(
        max_length=3,
        default='USD',
        help_text="Currency for all monetary values (enforced as USD)"
    )

    # Core GAM metrics
    impressions = models.BigIntegerField(
        default=0,
        help_text="Total impressions delivered"
    )
    revenue = models.DecimalField(
        max_digits=20, 
        decimal_places=2, 
        default=0,
        help_text="Total revenue in USD"
    )
    ecpm = models.DecimalField(
        max_digits=20, 
        decimal_places=2, 
        default=0,
        help_text="Effective CPM (revenue per 1000 impressions)"
    )
    clicks = models.BigIntegerField(
        default=0,
        help_text="Total clicks"
    )
    ctr = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Click-through rate as percentage"
    )
    eligible_ad_requests = models.BigIntegerField(
        default=0,
        help_text="Programmatic eligible ad requests"
    )
    viewable_impressions_rate = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=0,
        help_text="Viewable impressions rate as percentage"
    )
    total_ad_requests = models.BigIntegerField(
        default=0,
        help_text="Total ad requests"
    )

    # 🆕 UNKNOWN REVENUE TRACKING (for desktop devices marked as unknown)
    unknown_revenue = models.DecimalField(
        max_digits=20, 
        decimal_places=2, 
        default=0,
        help_text="Revenue from desktop devices marked as unknown"
    )
    unknown_impressions = models.BigIntegerField(
        default=0,
        help_text="Impressions from desktop devices marked as unknown"
    )
    unknown_clicks = models.BigIntegerField(
        default=0,
        help_text="Clicks from desktop devices marked as unknown"
    )
    unknown_ecpm = models.DecimalField(
        max_digits=20, 
        decimal_places=2, 
        default=0,
        help_text="eCPM from desktop devices marked as unknown"
    )
    unknown_ctr = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="CTR from desktop devices marked as unknown"
    )
    
    # Note: Using unknown fields for device category tracking

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "master_metadata"
        unique_together = ("invitation", "date", "dimension_type", "dimension_value")
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["dimension_type", "dimension_value"]),
            models.Index(fields=["parent_network"]),
            models.Index(fields=["child_network_code"]),
            models.Index(fields=["invitation"]),
            models.Index(fields=["partner_id"]),
            models.Index(fields=["date", "dimension_type", "partner_id"]),
            models.Index(fields=["parent_network", "date"]),
            models.Index(fields=["child_network_code", "date"]),
            # 🆕 New indexes for unknown metrics
            models.Index(fields=["date", "unknown_revenue"]),
            models.Index(fields=["child_network_code", "unknown_revenue"]),
        ]
        ordering = ['-date', 'dimension_type']

    def clean(self):
        """Model validation"""
        from django.core.exceptions import ValidationError

        # Validate currency is USD
        if self.currency and self.currency != 'USD':
            raise ValidationError({'currency': 'Only USD currency is supported'})

        # Validate dimension type
        valid_dimensions = [choice[0] for choice in DIMENSION_CHOICES]
        if self.dimension_type not in valid_dimensions:
            raise ValidationError({'dimension_type': f'Invalid dimension type. Must be one of: {valid_dimensions}'})

        # Validate numeric fields are non-negative
        numeric_fields = ['impressions', 'revenue', 'clicks', 'total_ad_requests', 'eligible_ad_requests']
        for field in numeric_fields:
            value = getattr(self, field, 0)
            if value < 0:
                raise ValidationError({field: f'{field} cannot be negative'})

    def save(self, *args, **kwargs):
        """Override save to ensure validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} | {self.child_network_code} | {self.dimension_type} | {self.dimension_value or 'overview'}"

    @property
    def fill_rate(self):
        """Calculate fill rate percentage"""
        if self.total_ad_requests > 0:
            return round((self.impressions / self.total_ad_requests) * 100, 2)
        return 0

    @property
    def revenue_usd(self):
        """Return revenue formatted as USD"""
        return f"{self.revenue:.2f}"

    # 🆕 Unknown revenue property for desktop devices
    @property 
    def unknown_revenue_usd(self):
        """Return unknown revenue formatted as USD"""
        return f"{self.unknown_revenue:.2f}"

    # 🆕 New calculated properties (Already present in your version ✅)
    @property
    def total_revenue_usd(self):
        """Return total revenue (matched + unknown) formatted as USD"""
        total = self.revenue + self.unknown_revenue
        return f"{total:.2f}"

    @property
    def match_rate(self):
        """Calculate match rate (matched impressions / total impressions)"""
        total_impressions = self.impressions + self.unknown_impressions
        if total_impressions > 0:
            return round((self.impressions / total_impressions) * 100, 2)
        return 0

    @property
    def unknown_fill_rate(self):
        """Calculate fill rate for unknown impressions"""
        if self.total_ad_requests > 0:
            return round((self.unknown_impressions / self.total_ad_requests) * 100, 2)
        return 0



class ReportSyncLog(models.Model):
    """
    Track cron job execution and sync status
    """
    SYNC_STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    ]

    # Sync metadata
    sync_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=SYNC_STATUS_CHOICES, default='running')
    
    # Date range processed
    date_from = models.DateField()
    date_to = models.DateField()
    
    # Execution tracking
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Results tracking
    total_networks_processed = models.IntegerField(default=0)
    successful_networks = models.IntegerField(default=0)
    failed_networks = models.IntegerField(default=0)
    total_records_created = models.IntegerField(default=0)
    total_records_updated = models.IntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    network_errors = models.JSONField(default=dict, blank=True)
    
    # Triggered by
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who triggered manual sync"
    )
    is_manual = models.BooleanField(default=False)

    class Meta:
        db_table = "report_sync_logs"
        ordering = ['-started_at']

    def __str__(self):
        return f"Sync {self.sync_id} - {self.status} ({self.date_from} to {self.date_to})"

    def mark_completed(self, successful_count, failed_count, total_records_created, total_records_updated):
        """Mark sync as completed with results"""
        self.completed_at = timezone.now()
        self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.successful_networks = successful_count
        self.failed_networks = failed_count
        self.total_networks_processed = successful_count + failed_count
        self.total_records_created = total_records_created
        self.total_records_updated = total_records_updated
        
        if failed_count == 0:
            self.status = 'completed'
        elif successful_count > 0:
            self.status = 'partial'
        else:
            self.status = 'failed'
        
        self.save()

    def add_network_error(self, network_code, error_message):
        """Add error for specific network"""
        if not self.network_errors:
            self.network_errors = {}
        self.network_errors[network_code] = str(error_message)
        self.save()