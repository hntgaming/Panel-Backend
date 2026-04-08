# reports/models.py

from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.conf import settings
from accounts.models import User

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

SOURCE_TYPE_CHOICES = [
    ('mcm_direct', 'MCM Direct'),
    ('gam360_passback', 'GAM 360 Passback'),
    ('prebid', 'Prebid'),
    ('open_bidding', 'Open Bidding'),
    ('adx_direct', 'AdX Direct'),
    ('house', 'House'),
    ('direct_campaign', 'Direct Campaign'),
    ('unknown', 'Unknown'),
]

PLATFORM_CHOICES = [
    ('web', 'Web'),
    ('app', 'App'),
    ('amp', 'AMP'),
    ('ctv', 'CTV'),
]


class Property(models.Model):
    """
    Internal property entity. Maps 1:1 to a domain or app bundle owned by a publisher.
    This is the canonical identity for attribution — not the GAM site dimension.
    """
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='properties',
        limit_choices_to={'role': 'publisher'},
    )
    property_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Internal property ID, e.g. prop_42_example_com",
    )
    domain = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Primary domain for web properties",
    )
    app_bundle = models.CharField(
        max_length=255,
        blank=True,
        help_text="App bundle ID for mobile properties",
    )
    platform = models.CharField(
        max_length=10,
        choices=PLATFORM_CHOICES,
        default='web',
    )
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('inactive', 'Inactive'), ('pending', 'Pending')],
        default='active',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tracking_properties'
        verbose_name_plural = 'Properties'
        indexes = [
            models.Index(fields=['publisher', 'status']),
            models.Index(fields=['domain']),
        ]

    def __str__(self):
        return f"{self.property_id} ({self.domain or self.app_bundle})"

    def save(self, *args, **kwargs):
        if not self.property_id:
            slug = (self.domain or self.app_bundle or 'unknown').replace('.', '_').replace('/', '_')
            self.property_id = f"prop_{self.publisher_id}_{slug}"
        super().save(*args, **kwargs)


class Placement(models.Model):
    """
    A specific ad slot on a property. Each placement maps to a GAM ad unit
    and carries a size, device target, and unique ID for attribution.
    """
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='placements',
    )
    placement_id = models.CharField(
        max_length=150,
        unique=True,
        db_index=True,
        help_text="Internal placement ID, e.g. plc_42_example_com_article_top_300x250",
    )
    placement_name = models.CharField(
        max_length=150,
        help_text="Human-readable name, e.g. Article Top 300x250",
    )
    ad_size = models.CharField(
        max_length=50,
        blank=True,
        help_text="Ad size, e.g. 300x250, 728x90, responsive",
    )
    device_type = models.CharField(
        max_length=20,
        choices=[('all', 'All'), ('desktop', 'Desktop'), ('mobile', 'Mobile'), ('tablet', 'Tablet')],
        default='all',
    )
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('inactive', 'Inactive'), ('pending', 'Pending')],
        default='active',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tracking_placements'
        indexes = [
            models.Index(fields=['property', 'status']),
        ]

    def __str__(self):
        return f"{self.placement_id} ({self.placement_name})"

    @cached_property
    def publisher(self):
        return self.property.publisher

    def save(self, *args, **kwargs):
        if not self.placement_id:
            prop_slug = self.property.property_id.replace('prop_', '')
            name_slug = self.placement_name.lower().replace(' ', '_').replace('-', '_')
            size_slug = self.ad_size.replace('x', 'x') if self.ad_size else ''
            self.placement_id = f"plc_{prop_slug}_{name_slug}_{size_slug}".rstrip('_')
        super().save(*args, **kwargs)


class GAMMapping(models.Model):
    """
    Maps GAM entities (ad units, line items, orders) to our internal
    publisher/property/placement identities. This is the bridge between
    GAM report data and our attribution system.
    """
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gam_mappings',
        null=True, blank=True,
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='gam_mappings',
    )
    placement = models.ForeignKey(
        Placement,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='gam_mappings',
    )
    gam_network_code = models.CharField(max_length=50, db_index=True)
    gam_ad_unit_path = models.CharField(
        max_length=500,
        blank=True,
        db_index=True,
        help_text="Full ad unit path, e.g. /23341212234/hnt/pub_42/prop_42_example_com/article_top_300x250",
    )
    gam_ad_unit_id = models.CharField(max_length=50, blank=True)
    gam_line_item_id = models.CharField(max_length=50, blank=True)
    gam_order_id = models.CharField(max_length=50, blank=True)
    source_type = models.CharField(
        max_length=30,
        choices=SOURCE_TYPE_CHOICES,
        default='unknown',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tracking_gam_mappings'
        indexes = [
            models.Index(fields=['gam_ad_unit_path']),
            models.Index(fields=['gam_ad_unit_id']),
            models.Index(fields=['gam_line_item_id']),
            models.Index(fields=['gam_network_code', 'gam_ad_unit_path']),
            models.Index(fields=['source_type']),
        ]

    def __str__(self):
        return f"{self.gam_ad_unit_path or self.gam_ad_unit_id} -> {self.placement or self.property or self.publisher}"


class SourceTypeRule(models.Model):
    """
    Rules for classifying demand source type based on GAM line item / order
    naming conventions or IDs. Evaluated in priority order.
    """
    MATCH_FIELD_CHOICES = [
        ('line_item_name', 'Line Item Name'),
        ('line_item_id', 'Line Item ID'),
        ('order_name', 'Order Name'),
        ('order_id', 'Order ID'),
        ('ad_unit_path', 'Ad Unit Path'),
        ('creative_name', 'Creative Name'),
    ]
    MATCH_TYPE_CHOICES = [
        ('contains', 'Contains'),
        ('startswith', 'Starts With'),
        ('exact', 'Exact Match'),
        ('regex', 'Regex'),
    ]

    priority = models.IntegerField(default=100, help_text="Lower = higher priority")
    match_field = models.CharField(max_length=30, choices=MATCH_FIELD_CHOICES)
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, default='contains')
    match_value = models.CharField(max_length=500)
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tracking_source_type_rules'
        ordering = ['priority']

    def __str__(self):
        return f"[{self.priority}] {self.match_field} {self.match_type} '{self.match_value}' -> {self.source_type}"

class MasterMetaData(models.Model):
    """
    Unified reporting table for GAM analytics
    Optimized with proper indexing and validation
    """
    # Source relationships - simplified for managed inventory
    parent_network_code = models.CharField(
        max_length=20,
        default='152344380',
        help_text="Parent GAM network code",
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

    # Unified tracking identity fields (nullable for backward compat with legacy data)
    property_id_tracking = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Internal property ID from tracking_properties",
    )
    placement_id_tracking = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        db_index=True,
        help_text="Internal placement ID from tracking_placements",
    )
    source_type = models.CharField(
        max_length=30,
        choices=SOURCE_TYPE_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text="Demand source classification",
    )
    attribution_method = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        choices=[
            ('key_value', 'Key-Value Match'),
            ('ad_unit_path', 'Ad Unit Path Parse'),
            ('gam_mapping', 'GAM Mapping Table'),
            ('domain_match', 'Domain Match'),
            ('legacy', 'Legacy Fallback'),
            ('unattributed', 'Unattributed'),
        ],
        help_text="How this record was attributed to publisher/property/placement",
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
        unique_together = ("child_network_code", "date", "dimension_type", "dimension_value")
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["dimension_type", "dimension_value"]),
            models.Index(fields=["parent_network_code"]),
            models.Index(fields=["child_network_code"]),
            models.Index(fields=["publisher_id"]),
            models.Index(fields=["date", "dimension_type", "publisher_id"]),
            models.Index(fields=["parent_network_code", "date"]),
            models.Index(fields=["child_network_code", "date"]),
            models.Index(fields=["property_id_tracking", "date"]),
            models.Index(fields=["placement_id_tracking", "date"]),
            models.Index(fields=["source_type", "date"]),
            models.Index(fields=["publisher_id", "property_id_tracking", "date"]),
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