# =============================================================================
# GAM REPORTS VIEWS - CLEANED AND OPTIMIZED
# =============================================================================
# This file contains all API views for GAM reporting functionality
# Includes: data listing, analytics, dashboard, export, and unified queries
# =============================================================================

from decimal import Decimal
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Sum, Avg, Q, F, Max, Min
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta, datetime
import csv
import logging

# Local imports
from accounts.models import User
from accounts.views import IsAdminUser
from .models import MasterMetaData, ReportSyncLog, MonthlyEarning
from .services import GAMReportService
from django.http import HttpResponse
from .serializers import (
    MasterMetaDataSerializer,
    ReportAnalyticsSerializer,
    ReportSyncLogSerializer,
    TriggerSyncSerializer,
    UnifiedReportsQuerySerializer,
    MonthlyEarningSerializer,
    MonthlyEarningAdminSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_cache_key(prefix, user_id, **kwargs):
    """
    Generate cache key for report data with consistent naming
    """
    key_parts = [prefix, str(user_id)]
    for k, v in sorted(kwargs.items()):
        if v is not None:
            key_parts.append(f"{k}_{v}")
    return "_".join(key_parts)


def apply_publisher_filter(queryset, user):
    """
    Apply role-based report filtering for both MCM and O&O publishers.
    MCM: filter by child_network_code = user.network_id
    O&O: filter by publisher_id = user.id
    """
    if user.is_admin_user:
        return queryset
    
    gam_type = getattr(user, 'gam_type', 'mcm') or 'mcm'
    
    if gam_type == 'o_and_o':
        return queryset.filter(publisher_id=user.id)
    else:
        if hasattr(user, 'network_id') and user.network_id:
            return queryset.filter(child_network_code=user.network_id)
        return queryset.none()


# =============================================================================
# MAIN REPORT VIEWS
# =============================================================================

class ReportDataListView(generics.ListAPIView):
    """
    GET /api/reports/data/ - List report data with optimized filtering and pagination
    
    Features:
    - Optimized queryset with select_related for performance
    - Partner-based access control (non-admin users see only assigned accounts)
    - Dimension type filtering
    - Date range filtering
    - Pagination support
    """
    serializer_class = MasterMetaDataSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = MasterMetaData.objects.all()
        queryset = apply_publisher_filter(queryset, self.request.user)
        
        # Apply filters
        parent_network = self.request.query_params.get('parent_network')
        if parent_network:
            queryset = queryset.filter(parent_network_code=parent_network)
        
        child_network = self.request.query_params.get('child_network')
        if child_network:
            queryset = queryset.filter(child_network_code=child_network)
        
        publisher_id = self.request.query_params.get('publisher')
        if publisher_id:
            queryset = queryset.filter(publisher_id=publisher_id)
        
        dimension_type = self.request.query_params.get('dimension_type')
        if dimension_type:
            queryset = queryset.filter(dimension_type=dimension_type)
        
        # Date filtering
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from and date_to:
            queryset = queryset.filter(date__range=[date_from, date_to])
        elif date_from:
            queryset = queryset.filter(date__gte=date_from)
        elif date_to:
            queryset = queryset.filter(date__lte=date_to)
        
        return queryset.order_by('-date', 'dimension_type')


# =============================================================================
# ANALYTICS AND DASHBOARD VIEWS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_analytics_view(request):
    """
    GET /api/reports/analytics/ - Comprehensive analytics for report data
    
    Returns:
    - Total revenue, impressions, clicks across all dimensions
    - Revenue statistics (total, average, min, max)
    - CTR calculations
    - Dimension breakdown
    - Partner-based access control
    """
    user = request.user
    
    base_queryset = apply_publisher_filter(MasterMetaData.objects.all(), user)
    
    # Date range (default to last 30 days)
    date_to = timezone.now().date()
    date_from = date_to - timedelta(days=30)
    
    date_from_param = request.query_params.get('date_from')
    date_to_param = request.query_params.get('date_to')
    
    if date_from_param:
        try:
            date_from = datetime.strptime(date_from_param, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    if date_to_param:
        try:
            date_to = datetime.strptime(date_to_param, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    # Filter by date range
    queryset = base_queryset.filter(date__range=[date_from, date_to])
    
    # Calculate analytics
    total_records = queryset.count()
    
    # Revenue analytics
    revenue_stats = queryset.aggregate(
        total_revenue=Sum('revenue'),
        avg_ecpm=Avg('ecpm'),
        total_impressions=Sum('impressions'),
        total_clicks=Sum('clicks'),
        total_ad_requests=Sum('total_ad_requests')
    )
    
    # Network breakdown
    network_breakdown = queryset.values(
        'parent_network_code'
    ).annotate(
        total_revenue=Sum('revenue'),
        total_impressions=Sum('impressions'),
        child_count=Count('child_network_code', distinct=True)
    ).order_by('-total_revenue')
    
    # Dimension breakdown
    dimension_breakdown = queryset.values('dimension_type').annotate(
        record_count=Count('id'),
        total_revenue=Sum('revenue'),
        avg_ecpm=Avg('ecpm')
    ).order_by('-total_revenue')
    
    # Partner performance (admin only)
    partner_breakdown = []
    if user.is_admin_user:
        partner_breakdown = queryset.filter(
            parent_network_code__isnull=False
        ).values('parent_network_code').annotate(
            total_revenue=Sum('revenue'),
            total_impressions=Sum('impressions'),
            child_count=Count('child_network_code', distinct=True)
        ).order_by('-total_revenue')
    
    # Recent sync status
    recent_syncs = ReportSyncLog.objects.order_by('-started_at')[:5]
    
    analytics_data = {
        'date_range': {
            'from': date_from,
            'to': date_to
        },
        'summary': {
            'total_records': total_records,
            'total_revenue': revenue_stats['total_revenue'] or 0,
            'total_impressions': revenue_stats['total_impressions'] or 0,
            'total_clicks': revenue_stats['total_clicks'] or 0,
            'total_ad_requests': revenue_stats['total_ad_requests'] or 0,
            'average_ecpm': revenue_stats['avg_ecpm'] or 0,
            'average_ctr': (revenue_stats['total_clicks'] / revenue_stats['total_impressions'] * 100) if revenue_stats['total_impressions'] else 0
        },
        'breakdowns': {
            'by_network': list(network_breakdown),
            'by_dimension': list(dimension_breakdown),
            'by_partner': list(partner_breakdown) if user.is_admin_user else []
        },
        'recent_syncs': ReportSyncLogSerializer(recent_syncs, many=True).data
    }
    
    return Response(analytics_data, status=status.HTTP_200_OK)


# Vetting analysis endpoint removed - not needed for Managed Inventory Publisher Dashboard


# =============================================================================
# SYNC AND ADMIN VIEWS
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAdminUser])
def trigger_sync_view(request):
    """
    POST /api/reports/trigger-sync/ - Manually trigger report sync (Admin only)
    
    Triggers GAM report fetching for all eligible accounts
    Returns sync status and job information
    """
    serializer = TriggerSyncSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    date_from = serializer.validated_data.get('date_from')
    date_to = serializer.validated_data.get('date_to')
    
    try:
        # Trigger sync in background (in production, use Celery)
        result = GAMReportService.fetch_gam_reports(
            date_from=date_from,
            date_to=date_to,
            triggered_by=request.user
        )
        
        return Response({
            'success': True,
            'message': 'Report sync triggered successfully',
            'sync_id': result['sync_id'],
            'result': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sync_status_view(request):
    """
    GET /api/reports/sync-status/ - Get sync job status
    """
    sync_id = request.query_params.get('sync_id')
    
    if sync_id:
        try:
            sync_log = ReportSyncLog.objects.get(sync_id=sync_id)
            return Response(ReportSyncLogSerializer(sync_log).data)
        except ReportSyncLog.DoesNotExist:
            return Response({'error': 'Sync job not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Return recent sync jobs
    recent_syncs = ReportSyncLog.objects.order_by('-started_at')[:10]
    return Response({
        'recent_syncs': ReportSyncLogSerializer(recent_syncs, many=True).data
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_dashboard_view(request):
    """
    GET /api/reports/dashboard/ - Dashboard overview with key metrics
    """
    user = request.user
    
    base_queryset = apply_publisher_filter(MasterMetaData.objects.all(), user)
    
    # Time periods
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Today's metrics
    today_data = base_queryset.filter(date=today, dimension_type='overview').aggregate(
        revenue=Sum('revenue'),
        impressions=Sum('impressions'),
        clicks=Sum('clicks'),
        ad_requests=Sum('total_ad_requests')
    )
    
    # Week's metrics
    week_data = base_queryset.filter(
        date__range=[week_ago, today], 
        dimension_type='overview'
    ).aggregate(
        revenue=Sum('revenue'),
        impressions=Sum('impressions'),
        clicks=Sum('clicks'),
        ad_requests=Sum('total_ad_requests')
    )
    
    # Month's metrics
    month_data = base_queryset.filter(
        date__range=[month_ago, today], 
        dimension_type='overview'
    ).aggregate(
        revenue=Sum('revenue'),
        impressions=Sum('impressions'),
        clicks=Sum('clicks'),
        ad_requests=Sum('total_ad_requests')
    )
    
    # Network counts
    if user.is_admin_user:
        from core.models import StatusChoices
        # Count active publishers with network_id
        total_networks = 1  # Parent network count (simplified for managed inventory)
        active_children = User.objects.filter(
            role=User.UserRole.PUBLISHER,
            status=StatusChoices.ACTIVE,
            network_id__isnull=False
        ).exclude(network_id='').count()
        total_partners = User.objects.filter(role=User.UserRole.PUBLISHER).count()
    else:
        # Partner view
        # Simplified for managed inventory - return default values
        total_networks = 0
        active_children = 0
        total_partners = 1  # Just themselves
    
    # Top performing networks (by revenue)
    top_networks = base_queryset.filter(
        date__range=[week_ago, today],
        dimension_type='overview'
    ).values(
        'parent_network_code'
    ).annotate(
        total_revenue=Sum('revenue'),
        total_impressions=Sum('impressions')
    ).order_by('-total_revenue')[:5]
    
    # Recent activity
    recent_activity = base_queryset.order_by('-created_at')[:10].values(
        'date', 'child_network_code', 'dimension_type', 
        'revenue', 'impressions', 'created_at'
    )
    
    dashboard_data = {
        'network_counts': {
            'total_networks': total_networks,
            'active_children': active_children,
            'total_partners': total_partners
        },
        'today_metrics': {
            'revenue': today_data['revenue'] or 0,
            'impressions': today_data['impressions'] or 0,
            'clicks': today_data['clicks'] or 0,
            'ad_requests': today_data['ad_requests'] or 0,
            'fill_rate': (today_data['impressions'] / today_data['ad_requests'] * 100) if today_data['ad_requests'] else 0
        },
        'week_metrics': {
            'revenue': week_data['revenue'] or 0,
            'impressions': week_data['impressions'] or 0,
            'clicks': week_data['clicks'] or 0,
            'ad_requests': week_data['ad_requests'] or 0,
            'avg_daily_revenue': (week_data['revenue'] / 7) if week_data['revenue'] else 0
        },
        'month_metrics': {
            'revenue': month_data['revenue'] or 0,
            'impressions': month_data['impressions'] or 0,
            'clicks': month_data['clicks'] or 0,
            'ad_requests': month_data['ad_requests'] or 0,
            'avg_daily_revenue': (month_data['revenue'] / 30) if month_data['revenue'] else 0
        },
        'top_performing_networks': list(top_networks),
        'recent_activity': list(recent_activity)
    }
    
    return Response(dashboard_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def realtime_ivt_check_view(request):
    """
    GET /api/reports/ivt/realtime/
    Optional params: child_network=<code>
    Performs quick heuristics over latest data to flag potential IVT risks.
    """
    child_code = request.query_params.get('child_network')

    base = apply_publisher_filter(MasterMetaData.objects.filter(dimension_type='overview'), request.user)
    if child_code:
        base = base.filter(child_network_code=child_code)

    if not base.exists():
        return Response({'error': 'No data available for the requested scope'}, status=404)

    today = timezone.now().date()
    d1 = today
    d7 = today - timedelta(days=7)

    # Today stats
    today_qs = base.filter(date=d1)
    t_agg = today_qs.aggregate(
        impressions=Coalesce(Sum('impressions'), 0),
        clicks=Coalesce(Sum('clicks'), 0),
        revenue=Coalesce(Sum('revenue'), 0.0),
        ecpm=Coalesce(Avg('ecpm'), 0.0),
        ctr=Coalesce(Avg('ctr'), 0.0),
        viewability=Coalesce(Avg('viewable_impressions_rate'), 0.0),
    )

    # Historical baseline (last 7 days excluding today)
    hist_qs = base.filter(date__range=[d7, today - timedelta(days=1)])
    h_agg = hist_qs.aggregate(
        impressions=Coalesce(Avg('impressions'), 0.0),
        clicks=Coalesce(Avg('clicks'), 0.0),
        revenue=Coalesce(Avg('revenue'), 0.0),
        ecpm=Coalesce(Avg('ecpm'), 0.0),
        ctr=Coalesce(Avg('ctr'), 0.0),
        viewability=Coalesce(Avg('viewable_impressions_rate'), 0.0),
    )

    # Heuristics
    ctr_today = float(t_agg['ctr'] or 0)
    ctr_base = float(h_agg['ctr'] or 0)
    ecpm_today = float(t_agg['ecpm'] or 0)
    ecpm_base = float(h_agg['ecpm'] or 0)
    view_today = float(t_agg['viewability'] or 0)

    flags = {
        'ctr_spike': (ctr_base > 0 and (ctr_today / ctr_base) > 2.0) or ctr_today > 3.0,
        'ecpm_spike': (ecpm_base > 0 and (ecpm_today / ecpm_base) > 2.0),
        'low_viewability': view_today < 25.0,
    }

    # Dimension concentration checks (today)
    def top_share(dim):
        dim_qs = apply_publisher_filter(
            MasterMetaData.objects.filter(dimension_type=dim, date=d1),
            request.user
        )
        if child_code:
            dim_qs = dim_qs.filter(child_network_code=child_code)
        total_imp = dim_qs.aggregate(val=Coalesce(Sum('impressions'), 0))['val'] or 0
        if total_imp == 0:
            return 0.0
        top_imp = dim_qs.order_by('-impressions').values_list('impressions', flat=True).first() or 0
        return float(top_imp) / float(total_imp)

    # Check site and country concentration (carrier removed for Managed Inventory)
    site_share = top_share('site')
    country_share = top_share('country')
    flags['site_concentration'] = site_share > 0.9
    flags['country_concentration'] = country_share > 0.9

    risk_score = 100
    for name, is_flag in flags.items():
        if is_flag:
            # Different weights
            risk_score -= 25 if name in ['ctr_spike'] else 15
    risk_score = max(0, risk_score)

    return Response({
        'scope': child_code or 'all',
        'today': {
            'impressions': t_agg['impressions'],
            'clicks': t_agg['clicks'],
            'revenue': float(t_agg['revenue']),
            'ecpm': ecpm_today,
            'ctr': ctr_today,
            'viewability': view_today,
        },
        'baseline_7d_avg': h_agg,
        'flags': flags,
        'risk_score': risk_score
    })


class ReportOverviewView(generics.ListAPIView):
    """
    GET /api/reports/overview/ - Overview reports with aggregation
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request, *args, **kwargs):
        user = request.user
        
        queryset = apply_publisher_filter(
            MasterMetaData.objects.filter(dimension_type='overview'), user
        )
        
        # Apply filters
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from and date_to:
            queryset = queryset.filter(date__range=[date_from, date_to])
        
        parent_network = request.query_params.get('parent_network')
        if parent_network:
            queryset = queryset.filter(parent_network_code=parent_network)
        
        # Group by date and aggregate
        daily_data = queryset.values('date').annotate(
            total_revenue=Sum('revenue'),
            total_impressions=Sum('impressions'),
            total_clicks=Sum('clicks'),
            total_ad_requests=Sum('total_ad_requests'),
            avg_ecpm=Avg('ecpm'),
            avg_ctr=Avg('ctr'),
            network_count=Count('parent_network_code', distinct=True),
            child_count=Count('child_network_code', distinct=True)
        ).order_by('-date')
        
        return Response({
            'daily_overview': list(daily_data),
            'summary': {
                'total_days': daily_data.count(),
                'total_revenue': sum(d['total_revenue'] or 0 for d in daily_data),
                'total_impressions': sum(d['total_impressions'] or 0 for d in daily_data),
                'avg_daily_revenue': sum(d['total_revenue'] or 0 for d in daily_data) / max(daily_data.count(), 1)
            }
        })


class ReportDetailedView(generics.ListAPIView):
    """
    GET /api/reports/detailed/ - Detailed reports with dimension breakdown
    """
    serializer_class = MasterMetaDataSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        queryset = apply_publisher_filter(MasterMetaData.objects.all(), user)
        
        # Apply filters
        dimension_type = self.request.query_params.get('dimension_type', 'overview')
        queryset = queryset.filter(dimension_type=dimension_type)
        
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from and date_to:
            queryset = queryset.filter(date__range=[date_from, date_to])
        
        parent_network = self.request.query_params.get('parent_network')
        if parent_network:
            queryset = queryset.filter(parent_network_code=parent_network)
        
        child_network = self.request.query_params.get('child_network')
        if child_network:
            queryset = queryset.filter(child_network_code=child_network)
        
        return queryset.order_by('-date', 'dimension_value')


# =============================================================================
# EXPORT AND UNIFIED QUERY VIEWS
# =============================================================================

class ReportExportView(generics.GenericAPIView):
    """
    GET /api/reports/export/ - Export report data as CSV
    
    Features:
    - CSV export with customizable fields
    - Partner-based access control
    - Dimension type filtering
    - Date range filtering
    - Proper CSV formatting with headers
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        
        user = request.user
        
        queryset = apply_publisher_filter(MasterMetaData.objects.all(), user)
        
        # Apply same filters as detailed view
        dimension_type = request.query_params.get('dimension_type', 'overview')
        queryset = queryset.filter(dimension_type=dimension_type)
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from and date_to:
            queryset = queryset.filter(date__range=[date_from, date_to])
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="gam_reports_{dimension_type}_{timezone.now().strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        
        # Write headers
        headers = [
            'Date', 'Parent Network', 'Child Network Code', 'Child Network Name',
            'Dimension Type', 'Dimension Value', 'Partner Email',
            'Impressions', 'Revenue (USD)', 'eCPM', 'Clicks', 'CTR (%)',
            'Eligible Ad Requests', 'Total Ad Requests', 'Fill Rate (%)',
            'Viewable Impressions Rate (%)'
        ]
        writer.writerow(headers)
        
        # Write data
        for record in queryset.order_by('-date', 'dimension_value'):
            partner_email = ''
            if record.publisher_id:
                try:
                    partner = User.objects.get(id=record.publisher_id)
                    partner_email = partner.email
                except User.DoesNotExist:
                    pass
            elif record.child_network_code:
                try:
                    partner = User.objects.get(network_id=record.child_network_code, role='publisher')
                    partner_email = partner.email
                except User.DoesNotExist:
                    pass
            
            writer.writerow([
                record.date,
                record.parent_network_code or '',
                record.child_network_code,
                record.parent_network_code or '',
                record.dimension_type,
                record.dimension_value or '',
                partner_email,
                record.impressions,
                f"{record.revenue:.2f}",
                f"{record.ecpm:.2f}",
                record.clicks,
                f"{record.ctr:.2f}",
                record.eligible_ad_requests,
                record.total_ad_requests,
                f"{record.fill_rate:.2f}",
                f"{record.viewable_impressions_rate:.2f}"
            ])
        
        return response
    

class UnifiedReportsQueryView(APIView):
    """
    POST /api/reports/query/ - Unified query interface for reports
    
    Features:
    - Flexible query interface with multiple response formats
    - Support for overview and detailed responses
    - CSV export capability
    - Partner-based access control
    - Dimension filtering
    - Date range filtering
    - Comprehensive metrics for managed inventory tracking
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = UnifiedReportsQuerySerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        
        try:
            # Build base queryset with role-based filtering
            queryset = self._build_base_queryset(request.user, validated_data)
            
            # Apply date filtering
            queryset = self._apply_date_filters(queryset, validated_data)
            
            # Apply dynamic filters
            queryset = self._apply_dynamic_filters(queryset, validated_data['filters'])
            
            # Apply dimension filtering
            queryset = self._apply_dimension_filters(queryset, validated_data['dimensions'])
            
            # Execute query based on query_type
            if validated_data['query_type'] == 'export':
                return self._export_csv_response(queryset, validated_data)
            elif validated_data['query_type'] == 'analytics':
                return self._analytics_response(queryset, validated_data)
            elif validated_data['query_type'] == 'overview':
                return self._overview_response(queryset, validated_data)
            else:  # detailed
                return self._detailed_response(queryset, validated_data)
                
        except Exception as e:
            return Response({
                'error': str(e),
                'message': 'Error processing report query'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _build_base_queryset(self, user, data):
        """Build base queryset with role-based access control for MCM and O&O"""
        queryset = MasterMetaData.objects.all()
        queryset = queryset.exclude(dimension_value__iexact='Total')
        queryset = apply_publisher_filter(queryset, user)
        return queryset
    
    def _apply_date_filters(self, queryset, data):
        """Apply date range filtering"""
        date_from = data['date_from']
        date_to = data['date_to']
        
        return queryset.filter(date__range=[date_from, date_to])
    
    def _apply_dynamic_filters(self, queryset, filters):
        """Apply dynamic filters from the filters object.
        child_network values match child_network_code in the DB:
          MCM -> the publisher's GAM network ID
          O&O -> the publisher's site domain
        Unified tracking filters: property_id, placement_id, source_type
        """
        for filter_key, filter_values in filters.items():
            if not filter_values:
                continue
            
            if filter_key == 'parent_network':
                queryset = queryset.filter(parent_network_code__in=filter_values)
            elif filter_key in ('publisher', 'child_network'):
                queryset = queryset.filter(child_network_code__in=filter_values)
            elif filter_key == 'dimension_type':
                queryset = queryset.filter(dimension_type__in=filter_values)
            elif filter_key == 'property_id':
                queryset = queryset.filter(property_id_tracking__in=filter_values)
            elif filter_key == 'placement_id':
                queryset = queryset.filter(placement_id_tracking__in=filter_values)
            elif filter_key == 'source_type':
                queryset = queryset.filter(source_type__in=filter_values)
        
        return queryset
    
    def _apply_dimension_filters(self, queryset, dimensions):
        """Apply dimension filtering"""
        if dimensions:
            return queryset.filter(dimension_type__in=dimensions)
        return queryset
    
    def _detailed_response(self, queryset, data):
        """Return detailed records with requested metrics"""
        # Order by date and dimension
        queryset = queryset.order_by('-date', 'dimension_type', 'dimension_value')

        paginate = data.get('paginate', True)
        if isinstance(paginate, str):
            paginate = paginate.lower() != 'false'

        # Build response data
        results = []
        metrics_list = data['metrics'].split(',')


        def serialize_record(record):
            result_data = {
                'id': record.id,
                'date': record.date,
                'dimension_type': record.dimension_type,
                'dimension_value': record.dimension_value,
                'parent_network_name': record.parent_network_code,
                'parent_network_code': record.parent_network_code,
                'child_network_code': record.child_network_code,
                'child_network_name': record.parent_network_code,
                'property_id': record.property_id_tracking,
                'placement_id': record.placement_id_tracking,
                'source_type': record.source_type,
                'attribution_method': record.attribution_method,
            }
            
            # Add requested metrics
            for metric in metrics_list:
                metric = metric.strip()
                # Use metric name directly - no mapping needed
                actual_metric = metric
                
                if hasattr(record, actual_metric):
                    value = getattr(record, actual_metric)
                    if metric in ['revenue']:
                        result_data[metric] = f"{value:.2f}"
                    else:
                        result_data[metric] = value
                elif metric == 'fill_rate':
                    result_data['fill_rate'] = record.fill_rate
                elif metric == 'revenue_usd':
                    result_data['revenue_usd'] = record.revenue_usd
                elif metric == 'total_revenue_usd':
                    result_data['total_revenue_usd'] = record.revenue_usd
            
            return result_data

        if paginate:
            from rest_framework.pagination import PageNumberPagination
            paginator = PageNumberPagination()
            paginator.page_size = int(self.request.query_params.get('page_size', 10000))
            page = paginator.paginate_queryset(queryset, self.request)
            for record in page:
                results.append(serialize_record(record))
            return paginator.get_paginated_response(results)
        else:
            for record in queryset.iterator():
                results.append(serialize_record(record))
            return Response({'results': results, 'count': len(results)})
    
    def _overview_response(self, queryset, data):
        """Return aggregated overview data with comprehensive metrics - Django compatible version"""
        
        # Parse requested metrics from the metrics string
        metrics_list = [m.strip() for m in data['metrics'].split(',')]
        
        # Group by date and get basic aggregations
        daily_data = queryset.values('date').annotate(
            total_revenue=Sum('revenue'),
            total_impressions=Sum('impressions'),
            total_clicks=Sum('clicks'),
            total_ad_requests=Sum('total_ad_requests'),
            total_eligible_ad_requests=Sum('eligible_ad_requests'),
            
            
            # Average metrics
            avg_ecpm=Avg('ecpm'),
            avg_ctr=Avg('ctr'),
            # Note: viewability will be calculated separately excluding zero-impression accounts
            
            # Counts
            network_count=Count('parent_network_code', distinct=True),
            child_count=Count('child_network_code', distinct=True)
        ).order_by('-date')
        
        # Format the response data with calculated metrics
        formatted_daily_data = []
        for day_data in daily_data:
            formatted_day = {
                'date': day_data['date'],
                'total_revenue': day_data['total_revenue'] or 0,
                'total_impressions': day_data['total_impressions'] or 0,
                'total_clicks': day_data['total_clicks'] or 0,
                'total_ad_requests': day_data['total_ad_requests'] or 0,
                'network_count': day_data['network_count'],
                'child_count': day_data['child_count']
            }
            
            # Add requested metrics to the response
            if 'ecpm' in metrics_list:
                formatted_day['avg_ecpm'] = round(day_data.get('avg_ecpm', 0) or 0, 4)
            
            if 'ctr' in metrics_list:
                formatted_day['avg_ctr'] = round(day_data.get('avg_ctr', 0) or 0, 4)
            
            if 'fill_rate' in metrics_list:
                # Calculate fill rate: impressions / total_ad_requests * 100
                total_requests = day_data.get('total_ad_requests', 0) or 0
                total_imps = day_data.get('total_impressions', 0) or 0
                fill_rate = (total_imps / total_requests * 100) if total_requests > 0 else 0
                formatted_day['avg_fill_rate'] = round(fill_rate, 2)
            
            if 'eligible_ad_requests' in metrics_list:
                formatted_day['total_eligible_ad_requests'] = day_data.get('total_eligible_ad_requests', 0) or 0
            
            if 'viewable_impressions_rate' in metrics_list:
                # Calculate viewability excluding zero-impression accounts
                date_value = day_data['date']
                accounts_with_impressions = queryset.filter(date=date_value, impressions__gt=0)
                if accounts_with_impressions.exists():
                    avg_viewability = accounts_with_impressions.aggregate(
                        avg_view=Avg('viewable_impressions_rate')
                    )['avg_view'] or 0
                    formatted_day['avg_viewable_impressions_rate'] = round(avg_viewability, 4)
                else:
                    formatted_day['avg_viewable_impressions_rate'] = 0
            
            
                matched_imps = day_data.get('total_impressions', 0) or 0
                total_all_imps = matched_imps
                match_rate = (matched_imps / total_all_imps * 100) if total_all_imps > 0 else 100
                formatted_day['avg_match_rate'] = round(match_rate, 2)
            
            if 'total_revenue_usd' in metrics_list:
                # Total revenue
                matched_rev = day_data.get('total_revenue', 0) or 0
                total_rev = matched_rev
                formatted_day['total_revenue_usd'] = f"{total_rev:.2f}"
            
            formatted_daily_data.append(formatted_day)
        
        # Calculate summary statistics
        summary_stats = {
            'total_days': len(formatted_daily_data),
            'total_revenue': sum(d['total_revenue'] for d in formatted_daily_data),
            'total_impressions': sum(d['total_impressions'] for d in formatted_daily_data),
            'avg_daily_revenue': sum(d['total_revenue'] for d in formatted_daily_data) / max(len(formatted_daily_data), 1)
        }
        
        # 🆕 ADD TOTAL ROW - Sum of all accounts data
        total_row = {
            'date': 'Total',
            'total_revenue': summary_stats['total_revenue'],
            'total_impressions': summary_stats['total_impressions'],
            'total_clicks': sum(d.get('total_clicks', 0) for d in formatted_daily_data),
            'total_ad_requests': sum(d.get('total_ad_requests', 0) for d in formatted_daily_data),
            'network_count': max(d.get('network_count', 0) for d in formatted_daily_data) if formatted_daily_data else 0,
            'child_count': max(d.get('child_count', 0) for d in formatted_daily_data) if formatted_daily_data else 0
        }
        
        # Add calculated metrics to total row
        if 'ecpm' in metrics_list:
            total_revenue = total_row['total_revenue']
            total_impressions = total_row['total_impressions']
            total_ecpm = (total_revenue / total_impressions * 1000) if total_impressions > 0 else 0
            total_row['avg_ecpm'] = round(total_ecpm, 4)
        
        if 'ctr' in metrics_list:
            total_clicks = total_row['total_clicks']
            total_impressions = total_row['total_impressions']
            total_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            total_row['avg_ctr'] = round(total_ctr, 4)
        
        if 'fill_rate' in metrics_list:
            total_requests = total_row['total_ad_requests']
            total_imps = total_row['total_impressions']
            total_fill_rate = (total_imps / total_requests * 100) if total_requests > 0 else 0
            total_row['avg_fill_rate'] = round(total_fill_rate, 2)
        
        
        
        if 'match_rate' in metrics_list:
            matched_imps = total_row['total_impressions']
            total_all_imps = matched_imps
            total_match_rate = (matched_imps / total_all_imps * 100) if total_all_imps > 0 else 100
            total_row['avg_match_rate'] = round(total_match_rate, 2)
        
        if 'total_revenue_usd' in metrics_list:
            matched_rev = total_row['total_revenue']
            total_rev = matched_rev
            total_row['total_revenue_usd'] = f"{total_rev:.2f}"
        
        # Note: Total row is now handled by frontend calculateTotals function
        # No need to add total row here - frontend will handle it like other tabs
        
        
        if 'total_revenue_usd' in metrics_list:
            total_rev_sum = 0
            for d in formatted_daily_data:
                rev_val = d.get('total_revenue_usd', '0')
                if isinstance(rev_val, str):
                    total_rev_sum += float(rev_val.replace(',', ''))
                else:
                    total_rev_sum += float(rev_val or 0)
            summary_stats['total_revenue'] = f"{total_rev_sum:.2f}"
        
        return Response({
            'query_info': {
                'date_from': data.get('date_from', 'N/A'),
                'date_to': data.get('date_to', 'N/A'),
                'filters_applied': data.get('filters', []),
                'dimensions': data.get('dimensions', []),
                'metrics': data.get('metrics', '')
            },
            'daily_overview': formatted_daily_data,
            'summary': summary_stats
        })
    
    def _analytics_response(self, queryset, data):
        """Return comprehensive analytics"""
        # Overall summary
        summary = queryset.aggregate(
            total_records=Count('id'),
            total_revenue=Sum('revenue'),
            total_impressions=Sum('impressions'),
            total_clicks=Sum('clicks'),
            total_ad_requests=Sum('total_ad_requests'),
            avg_ecpm=Avg('ecpm'),
            avg_ctr=Avg('ctr')
        )
        
        # Breakdown by network
        network_breakdown = queryset.values(
            'parent_network_code'
        ).annotate(
            total_revenue=Sum('revenue'),
            total_impressions=Sum('impressions'),
            child_count=Count('child_network_code', distinct=True)
        ).order_by('-total_revenue')
        
        # Breakdown by dimension
        dimension_breakdown = queryset.values('dimension_type').annotate(
            record_count=Count('id'),
            total_revenue=Sum('revenue'),
            avg_ecpm=Avg('ecpm')
        ).order_by('-total_revenue')
        
        return Response({
            'query_info': {
                'date_from': data['date_from'],
                'date_to': data['date_to'],
                'filters_applied': data['filters'],
                'total_records_found': summary['total_records']
            },
            'summary': summary,
            'breakdowns': {
                'by_network': list(network_breakdown),
                'by_dimension': list(dimension_breakdown)
            }
        })
    
    def _export_csv_response(self, queryset, data):
        """Return CSV export"""
        queryset = queryset.order_by('-date', 'dimension_type', 'dimension_value')
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="gam_reports_{data["date_from"]}_{data["date_to"]}.csv"'
        
        writer = csv.writer(response)
        
        # Write headers
        headers = [
            'Date', 'Parent Network', 'Child Network Code', 'Child Network Name',
            'Dimension Type', 'Dimension Value', 'Partner ID'
        ]
        
        # Add metric headers based on requested metrics
        metrics_list = data['metrics'].split(',')
        for metric in metrics_list:
            metric = metric.strip()
            if metric == 'revenue':
                headers.append('Revenue (USD)')
            elif metric == 'impressions':
                headers.append('Impressions')
            elif metric == 'ecpm':
                headers.append('eCPM')
            elif metric == 'clicks':
                headers.append('Clicks')
            elif metric == 'ctr':
                headers.append('CTR (%)')
            elif metric == 'fill_rate':
                headers.append('Fill Rate (%)')
            elif metric == 'total_ad_requests':
                headers.append('Total Ad Requests')
        
        writer.writerow(headers)
        
        # Write data
        for record in queryset:
            row = [
                record.date,
                record.parent_network_code or '',
                record.child_network_code,
                record.parent_network_code or '',
                record.dimension_type,
                record.dimension_value or '',
                record.parent_network_code or ''
            ]
            
            # Add metric values
            for metric in metrics_list:
                metric = metric.strip()
                if metric == 'revenue':
                    row.append(f"{record.revenue:.2f}")
                elif metric == 'impressions':
                    row.append(record.impressions)
                elif metric == 'ecpm':
                    row.append(f"{record.ecpm:.2f}")
                elif metric == 'clicks':
                    row.append(record.clicks)
                elif metric == 'ctr':
                    row.append(f"{record.ctr:.2f}")
                elif metric == 'fill_rate':
                    row.append(f"{record.fill_rate:.2f}")
                elif metric == 'total_ad_requests':
                    row.append(record.total_ad_requests)
            
            writer.writerow(row)
        
        return response


# =============================================================================
# FINANCIAL SUMMARY VIEW
# =============================================================================

@api_view(['POST', 'GET'])
@permission_classes([IsAuthenticated])
def financial_summary_view(request):
    """
    GET/POST /api/reports/financial-summary/ - Financial summary for revenue sharing
    
    Calculates gross revenue and parent share based on:
    - Date range filtering
    - Partner-based access control
    - Revenue aggregation across all dimensions
    - Parent network revenue sharing calculations
    """
    user = request.user
    
    # Get date range from request (support both POST and GET)
    if request.method == 'POST':
        date_from = request.data.get('date_from')
        date_to = request.data.get('date_to')
    else:  # GET request
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
    
    if not date_from or not date_to:
        return Response({'error': 'date_from and date_to are required'}, status=400)
    
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    except ValueError:
        return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    
    base_queryset = apply_publisher_filter(
        MasterMetaData.objects.filter(date__range=[date_from, date_to], dimension_type='overview'),
        user
    )
    
    # Calculate gross revenue (only from overview dimension to avoid double counting)
    gross_revenue = base_queryset.filter(
        dimension_type='overview'
    ).aggregate(
        total=Sum('revenue')
    )['total'] or 0
    
    # Calculate parent share based on user's specific revenue share percentage
    parent_share = 0
    
    if not user.is_admin_user and hasattr(user, 'revenue_share_percentage'):
        # Use the specific user's revenue share percentage
        user_revenue_share = user.revenue_share_percentage or 0
        if user_revenue_share > 0:
            parent_share = (gross_revenue * Decimal(str(user_revenue_share)) / 100)
        else:
            # Default to 20% if no revenue share is set
            parent_share = (gross_revenue * Decimal('0.20'))
    else:
        # For admin users, use default 20%
        parent_share = (gross_revenue * Decimal('0.20'))
    
    return Response({
        'gross_revenue': float(gross_revenue),
        'parent_share': float(parent_share),
        'date_from': date_from.strftime('%Y-%m-%d'),
        'date_to': date_to.strftime('%Y-%m-%d')
    })


# =============================================================================
# MONTHLY EARNINGS VIEWS
# =============================================================================

class MonthlyEarningListView(generics.ListAPIView):
    """
    GET /api/reports/earnings/
    Publishers see only their own records.  Admins see all.
    Supports ?month=YYYY-MM-DD and ?status=pending|processing|paid filters.
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.user.is_admin_user:
            return MonthlyEarningAdminSerializer
        return MonthlyEarningSerializer

    def get_queryset(self):
        user = self.request.user
        qs = MonthlyEarning.objects.select_related('publisher')

        if not user.is_admin_user:
            qs = qs.filter(publisher=user)

        month = self.request.query_params.get('month')
        if month:
            qs = qs.filter(month=month)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        publisher_id = self.request.query_params.get('publisher')
        if publisher_id and user.is_admin_user:
            qs = qs.filter(publisher_id=publisher_id)

        return qs.order_by('-month', 'publisher__email')


class MonthlyEarningDetailView(generics.RetrieveUpdateAPIView):
    """
    GET / PATCH /api/reports/earnings/<pk>/
    Admin can update ivt_deduction, parent_share, status, notes.
    Publishers can only GET their own record.
    """
    permission_classes = [IsAuthenticated]
    queryset = MonthlyEarning.objects.select_related('publisher')

    def get_serializer_class(self):
        if self.request.user.is_admin_user:
            return MonthlyEarningAdminSerializer
        return MonthlyEarningSerializer

    def get_queryset(self):
        user = self.request.user
        qs = MonthlyEarning.objects.select_related('publisher')
        if not user.is_admin_user:
            qs = qs.filter(publisher=user)
        return qs

    def perform_update(self, serializer):
        instance = serializer.save()
        instance.recalculate_net()
        instance.save()


class GenerateMonthlyEarningsView(APIView):
    """
    POST /api/reports/earnings/generate/
    Admin-only.  Body: { "month": "YYYY-MM-DD" }
    Auto-calculates gross_revenue and total_impressions from MasterMetaData
    for each publisher that has overview data in that month.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        month_str = request.data.get('month')
        if not month_str:
            return Response({'error': 'month is required (YYYY-MM-DD, first of month)'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            month_date = datetime.strptime(month_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'},
                            status=status.HTTP_400_BAD_REQUEST)

        month_date = month_date.replace(day=1)

        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1, day=1)

        publishers = User.objects.filter(role=User.UserRole.PUBLISHER)

        created_count = 0
        updated_count = 0

        for pub in publishers:
            qs = MasterMetaData.objects.filter(
                dimension_type='overview',
                date__gte=month_date,
                date__lt=next_month,
            )

            gam_type = getattr(pub, 'gam_type', 'mcm') or 'mcm'
            if gam_type == 'o_and_o':
                qs = qs.filter(publisher_id=pub.id)
            else:
                if pub.network_id:
                    qs = qs.filter(child_network_code=pub.network_id)
                else:
                    continue

            agg = qs.aggregate(
                gross=Coalesce(Sum('revenue'), Decimal('0')),
                imps=Coalesce(Sum('impressions'), 0),
            )

            gross = agg['gross']
            imps = agg['imps']

            if gross == 0 and imps == 0:
                continue

            earning, created = MonthlyEarning.objects.get_or_create(
                publisher=pub,
                month=month_date,
                defaults={
                    'gross_revenue': gross,
                    'total_impressions': imps,
                }
            )

            if not created:
                earning.gross_revenue = gross
                earning.total_impressions = imps

            earning.recalculate_net()
            earning.save()

            if created:
                created_count += 1
            else:
                updated_count += 1

        return Response({
            'success': True,
            'month': month_date.isoformat(),
            'created': created_count,
            'updated': updated_count,
        }, status=status.HTTP_200_OK)


class BulkUpdateEarningsView(APIView):
    """
    POST /api/reports/earnings/bulk-update/
    Admin-only.  Body: { "ids": [1,2,...], "status": "paid" }
    Allows batch status updates.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        ids = request.data.get('ids', [])
        new_status = request.data.get('status')

        if not ids:
            return Response({'error': 'ids list is required'}, status=status.HTTP_400_BAD_REQUEST)

        valid_statuses = [s[0] for s in MonthlyEarning.Status.choices]
        if new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Must be one of: {valid_statuses}'},
                            status=status.HTTP_400_BAD_REQUEST)

        updated = MonthlyEarning.objects.filter(id__in=ids).update(status=new_status)

        return Response({
            'success': True,
            'updated': updated,
        }, status=status.HTTP_200_OK)

