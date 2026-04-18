from django.urls import path
from . import views
app_name = 'reports'
urlpatterns = [
    path(
        'trigger-sync/', 
        views.trigger_sync_view, 
        name='trigger-sync'
    ),
    path(
        'sync-status/', 
        views.sync_status_view, 
        name='sync-status'
    ),
    path(
        'data/', 
        views.ReportDataListView.as_view(), 
        name='report-data'
    ),
    path(
        'analytics/', 
        views.report_analytics_view, 
        name='report-analytics'
    ),
    path(
        'dashboard/', 
        views.report_dashboard_view, 
        name='report-dashboard'
    ),
    path(
        'overview/', 
        views.ReportOverviewView.as_view(), 
        name='report-overview'
    ),
    path(
        'detailed/', 
        views.ReportDetailedView.as_view(), 
        name='report-detailed'
    ),
    path(
        'export/', 
        views.ReportExportView.as_view(), 
        name='report-export'
    ),
    path(
        'query/', 
        views.UnifiedReportsQueryView.as_view(), 
        name='unified-query'
    ),
    path(
        'financial-summary/', 
        views.financial_summary_view, 
        name='financial-summary'
    ),
    path(
        'ivt/realtime/',
        views.realtime_ivt_check_view,
        name='realtime-ivt-check'
    ),
    path(
        'earnings/',
        views.MonthlyEarningListView.as_view(),
        name='earnings-list'
    ),
    path(
        'earnings/generate/',
        views.GenerateMonthlyEarningsView.as_view(),
        name='earnings-generate'
    ),
    path(
        'earnings/bulk-update/',
        views.BulkUpdateEarningsView.as_view(),
        name='earnings-bulk-update'
    ),
    path(
        'earnings/<int:pk>/',
        views.MonthlyEarningDetailView.as_view(),
        name='earnings-detail'
    ),

    # Sub-publisher earnings
    path('sub-publisher-earnings/', views.sub_publisher_earnings_view, name='sub-publisher-earnings'),
    path('calculate-sub-publisher-earnings/', views.calculate_sub_publisher_earnings_view, name='calculate-sub-publisher-earnings'),
    path('partner-rollup/', views.partner_rollup_view, name='partner-rollup'),
]