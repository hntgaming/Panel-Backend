# reports/serializers.py - COMPLETE FILE with New Unmatched Metrics

from rest_framework import serializers
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from django.utils import timezone

# Removed gam_accounts dependencies
from .models import MasterMetaData, ReportSyncLog

User = get_user_model()


class MasterMetaDataSerializer(serializers.ModelSerializer):
    """
    🆕 UPDATED: Serializer for MasterMetaData with enhanced fields and new unknown metrics
    """
    parent_network_name = serializers.CharField(source='parent_network.network_name', read_only=True)
    parent_network_code = serializers.CharField(source='parent_network.network_code', read_only=True)
    child_network_name = serializers.CharField(source='invitation.child_network_name', read_only=True)
    
    # Existing calculated fields
    fill_rate = serializers.ReadOnlyField()
    revenue_usd = serializers.ReadOnlyField()
    
    # Calculated fields for unknown revenue
    # Unknown metrics removed for Managed Inventory Publisher Dashboard
    total_revenue_usd = serializers.ReadOnlyField()

    # Partner information
    partner_email = serializers.SerializerMethodField()
    partner_name = serializers.SerializerMethodField()

    class Meta:
        model = MasterMetaData
        fields = [
            'id', 'date', 'dimension_type', 'dimension_value', 'currency',
            'parent_network', 'parent_network_name', 'parent_network_code',
            'invitation', 'child_network_code', 'child_network_name',
            'partner_id', 'partner_email', 'partner_name',
            
            # Existing metrics
            'impressions', 'revenue', 'revenue_usd', 'ecpm', 'clicks', 'ctr',
            'eligible_ad_requests', 'viewable_impressions_rate', 'total_ad_requests',
            'fill_rate',
            
            # Unknown metrics removed for Managed Inventory Publisher Dashboard
            'total_revenue_usd',
            
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_partner_email(self, obj):
        """Get partner email if assigned"""
        if obj.partner_id:
            try:
                user = User.objects.get(id=obj.partner_id)
                return user.email
            except User.DoesNotExist:
                return None
        return None

    def get_partner_name(self, obj):
        """Get partner full name if assigned"""
        if obj.partner_id:
            try:
                user = User.objects.get(id=obj.partner_id)
                return user.get_full_name()
            except User.DoesNotExist:
                return None
        return None


class ReportAnalyticsSerializer(serializers.Serializer):
    """
    Serializer for report analytics data
    """
    total_impressions = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=20, decimal_places=8)
    total_clicks = serializers.IntegerField()
    average_ctr = serializers.DecimalField(max_digits=10, decimal_places=4)
    average_ecpm = serializers.DecimalField(max_digits=10, decimal_places=4)
    # Unknown metrics fields removed for Managed Inventory Publisher Dashboard
    total_networks = serializers.IntegerField()
    total_records = serializers.IntegerField()


class TriggerSyncSerializer(serializers.Serializer):
    """
    Serializer for triggering report sync
    """
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    force_refresh = serializers.BooleanField(default=False)
    
    def validate(self, data):
        """Validate date range"""
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("date_from cannot be after date_to")
        
        return data


class UnifiedReportsQuerySerializer(serializers.Serializer):
    """
    Serializer for unified reports query
    """
    # Date range
    date_from = serializers.DateField(
        required=False,
        help_text="Start date (YYYY-MM-DD)"
    )
    date_to = serializers.DateField(
        required=False, 
        help_text="End date (YYYY-MM-DD)"
    )
    
    # Timeframe selection
    timeframe = serializers.ChoiceField(
        choices=[
            ('month_to_date', 'Month to Date'),
            ('last_month', 'Last Month'),
            ('last_3_months', 'Last 3 Months'),
            ('last_6_months', 'Last 6 Months'),
        ],
        required=False,
        default='month_to_date',
        help_text="Predefined timeframe for the report"
    )
    
    # Dimensions array - Updated for Managed Inventory Publisher Dashboard
    dimensions = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            ('overview', 'Overview'),
            ('site', 'Site'),
            ('trafficSource', 'Traffic Source'),
            ('deviceCategory', 'Device Category'),
            ('country', 'Country'),
            ('adunit', 'Ad Unit Name'),
            ('inventoryFormat', 'Inventory Format'),
            ('browser', 'Browser'),
        ]),
        required=False,
        default=['overview'],
        help_text="List of dimensions to include in the report"
    )
    
    # Metrics string (comma-separated) - Updated for Managed Inventory Publisher Dashboard
    metrics = serializers.CharField(
        required=False,
        default="impressions,revenue,ecpm,clicks,ctr,fill_rate,total_ad_requests,viewable_impressions_rate",
        help_text="Comma-separated list of metrics to include (unknown metrics removed)"
    )
    
    # Filters object
    filters = serializers.DictField(
        required=False,
        default=dict,
        help_text="Dictionary of filters to apply"
    )
    
    # Query type
    query_type = serializers.ChoiceField(
        choices=[
            ('overview', 'Overview'),
            ('detailed', 'Detailed'),
            ('analytics', 'Analytics'),
            ('export', 'Export'),
        ],
        required=False,
        default='detailed',
        help_text="Type of query to execute"
    )
    
    def validate_metrics(self, value):
        """Validate metrics string - unknown metrics removed"""
        valid_metrics = [
            'impressions', 'revenue', 'ecpm', 'clicks', 'ctr', 'fill_rate',
            'total_ad_requests', 'viewable_impressions_rate'
        ]
        
        metrics_list = [m.strip() for m in value.split(',')]
        for metric in metrics_list:
            if metric not in valid_metrics:
                raise serializers.ValidationError(f"Invalid metric: {metric}")
        
        return value
    
    def validate(self, data):
        """Set date range based on timeframe if not provided"""
        from datetime import datetime, timedelta
        
        timeframe = data.get('timeframe', 'month_to_date')
        now = datetime.now()
        
        if not data.get('date_from') or not data.get('date_to'):
            if timeframe == 'month_to_date':
                data['date_from'] = now.replace(day=1).date()
                data['date_to'] = now.date()
            elif timeframe == 'last_month':
                last_month = now.replace(day=1) - timedelta(days=1)
                data['date_from'] = last_month.replace(day=1).date()
                data['date_to'] = last_month.date()
            elif timeframe == 'last_3_months':
                data['date_from'] = (now - timedelta(days=90)).date()
                data['date_to'] = now.date()
            elif timeframe == 'last_6_months':
                data['date_from'] = (now - timedelta(days=180)).date()
                data['date_to'] = now.date()
        
        return data


class ReportSyncLogSerializer(serializers.ModelSerializer):
    """
    Serializer for ReportSyncLog
    """
    triggered_by_email = serializers.CharField(source='triggered_by.email', read_only=True)
    duration_minutes = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()

    class Meta:
        model = ReportSyncLog
        fields = [
            'id', 'sync_id', 'status', 'date_from', 'date_to',
            'started_at', 'completed_at', 'duration_seconds', 'duration_minutes',
            'total_networks_processed', 'successful_networks', 'failed_networks',
            'total_records_created', 'total_records_updated',
            'error_message', 'network_errors', 'triggered_by', 'triggered_by_email',
            'is_manual', 'success_rate'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'duration_seconds']

    def get_duration_minutes(self, obj):
        """Convert duration from seconds to minutes"""
        if obj.duration_seconds:
            return round(obj.duration_seconds / 60, 2)
        return None

    def get_success_rate(self, obj):
        """Calculate success rate percentage"""
        if obj.total_networks_processed > 0:
            return round((obj.successful_networks / obj.total_networks_processed) * 100, 2)
        return 0
