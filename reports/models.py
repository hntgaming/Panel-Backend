# reports/models.py

from django.db import models
from django.utils import timezone
from django.conf import settings

DIMENSION_CHOICES = [
    ('overview', 'Overview'),
    ('site', 'App / Site'),
    ('trafficSource', 'Traffic Source'),
    ('deviceCategory', 'Device Category'),
    ('country', 'Country'),
    ('adunit', 'Ad Unit Name'),
    ('inventoryFormat', 'Inventory Format'),
    ('browser', 'Browser'),
]

class MasterMetaData(models.Model):
    """
    Unified reporting table for GAM analytics.
    Each partner admin connects their own GAM account; reports are fetched directly.
    """
    network_code = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Partner's GAM network code (from GAMCredential)"
    )
    publisher_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Partner admin user ID who owns this GAM account"
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

    # Unknown metrics removed for Managed Inventory Publisher Dashboard

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "master_metadata"
        unique_together = ("network_code", "date", "dimension_type", "dimension_value")
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["dimension_type", "dimension_value"]),
            models.Index(fields=["network_code"]),
            models.Index(fields=["publisher_id"]),
            models.Index(fields=["date", "dimension_type", "publisher_id"]),
            models.Index(fields=["network_code", "date"]),
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
        """Validate before single-record saves; bulk paths bypass this."""
        if not kwargs.pop('skip_validation', False):
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} | {self.network_code} | {self.dimension_type} | {self.dimension_value or 'overview'}"

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

    # Unknown metrics properties removed for Managed Inventory Publisher Dashboard



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


class MonthlyEarning(models.Model):
    """
    Monthly earnings / invoice record per publisher.
    gross_revenue and total_impressions are auto-calculated from MasterMetaData.
    IVT deduction, parent share, and status are managed by admin.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        PAID = 'paid', 'Paid'

    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='earnings',
    )
    month = models.DateField(
        help_text="First day of the month, e.g. 2026-03-01",
    )

    gross_revenue = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    total_impressions = models.BigIntegerField(default=0)

    ivt_deduction = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    parent_share = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    net_earnings = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'report_monthly_earnings'
        unique_together = ['publisher', 'month']
        ordering = ['-month', 'publisher__email']
        indexes = [
            models.Index(fields=['publisher', '-month']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.publisher.email} | {self.month.strftime('%b %Y')} | {self.status}"

    def recalculate_net(self):
        self.net_earnings = self.gross_revenue - self.ivt_deduction - self.parent_share
        return self.net_earnings


class SubPublisherEarning(models.Model):
    """
    Earnings record per sub-publisher per date.
    Derived from MasterMetaData by matching subdomain tracking assignments
    against GAM report site dimension values. Fee is snapshotted at calculation
    time for audit trail integrity.
    """

    sub_publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sub_publisher_earnings',
        limit_choices_to={'role': 'sub_publisher'},
    )
    partner_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='managed_sub_publisher_earnings',
        limit_choices_to={'role__in': ['partner_admin', 'admin']},
    )
    tracking_assignment = models.ForeignKey(
        'accounts.TrackingAssignment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='earnings',
    )

    date = models.DateField(db_index=True)

    gross_revenue = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Fee percentage snapshot at calculation time"
    )
    fee_amount = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    net_revenue = models.DecimalField(max_digits=20, decimal_places=6, default=0)

    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    ecpm = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    source_dimension_type = models.CharField(
        max_length=32, blank=True, default='',
        help_text="Dimension type used for matching (e.g. 'site', 'trafficSource')"
    )
    source_dimension_value = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Dimension value that matched the tracking assignment"
    )

    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'report_sub_publisher_earnings'
        unique_together = ['sub_publisher', 'date']
        ordering = ['-date', 'sub_publisher__email']
        indexes = [
            models.Index(fields=['sub_publisher', '-date']),
            models.Index(fields=['partner_admin', '-date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return (
            f"{self.sub_publisher.email} | {self.date} | "
            f"gross={self.gross_revenue} fee={self.fee_amount} net={self.net_revenue}"
        )

    def calculate_net(self):
        from decimal import Decimal
        self.fee_amount = (self.gross_revenue * self.fee_percentage / Decimal('100')).quantize(Decimal('0.000001'))
        self.net_revenue = self.gross_revenue - self.fee_amount
        if self.impressions > 0:
            self.ecpm = (self.gross_revenue / self.impressions * 1000).quantize(Decimal('0.01'))
        return self.net_revenue