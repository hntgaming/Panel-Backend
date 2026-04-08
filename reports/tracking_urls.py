# reports/tracking_urls.py

from django.urls import path
from . import tracking_views as views

app_name = 'tracking'

urlpatterns = [
    # Property CRUD
    path('properties/', views.PropertyListCreateView.as_view(), name='property-list'),
    path('properties/<int:pk>/', views.PropertyDetailView.as_view(), name='property-detail'),

    # Placement CRUD
    path('placements/', views.PlacementListCreateView.as_view(), name='placement-list'),
    path('placements/<int:pk>/', views.PlacementDetailView.as_view(), name='placement-detail'),

    # GAM Mapping CRUD (admin only)
    path('gam-mappings/', views.GAMMappingListCreateView.as_view(), name='gam-mapping-list'),
    path('gam-mappings/<int:pk>/', views.GAMMappingDetailView.as_view(), name='gam-mapping-detail'),

    # Source Type Rules (admin only)
    path('source-rules/', views.SourceTypeRuleListCreateView.as_view(), name='source-rule-list'),
    path('source-rules/<int:pk>/', views.SourceTypeRuleDetailView.as_view(), name='source-rule-detail'),

    # Tag generation
    path('tags/gpt/', views.GenerateGPTTagView.as_view(), name='generate-gpt-tag'),
    path('tags/passback/', views.GeneratePassbackTagView.as_view(), name='generate-passback-tag'),
    path('tags/ad-unit-path/', views.GenerateAdUnitPathView.as_view(), name='generate-ad-unit-path'),

    # Auto-setup
    path('auto-setup/', views.AutoCreatePropertyPlacementsView.as_view(), name='auto-setup'),
]
