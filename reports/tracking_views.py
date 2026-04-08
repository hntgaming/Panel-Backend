# reports/tracking_views.py
#
# API views for unified tracking: Property, Placement, GAMMapping CRUD
# and tag generation endpoints.

import logging
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.views import IsAdminUser
from .models import Property, Placement, GAMMapping, SourceTypeRule
from .tracking_serializers import (
    PropertySerializer,
    PlacementSerializer,
    GAMMappingSerializer,
    SourceTypeRuleSerializer,
    TagGenerationSerializer,
    PassbackTagSerializer,
)
from .tag_generator import (
    generate_gpt_tag,
    generate_passback_tag,
    generate_multi_slot_page,
    generate_ad_unit_path,
)
from .attribution import invalidate_attribution_cache

logger = logging.getLogger(__name__)


# =============================================================================
# PROPERTY VIEWS
# =============================================================================

class PropertyListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/reports/tracking/properties/      - List properties
    POST /api/reports/tracking/properties/      - Create a property
    Admin sees all; publisher sees own.
    """
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Property.objects.select_related('publisher').prefetch_related('placements')
        if not self.request.user.is_admin_user:
            qs = qs.filter(publisher=self.request.user)

        publisher_id = self.request.query_params.get('publisher')
        if publisher_id and self.request.user.is_admin_user:
            qs = qs.filter(publisher_id=publisher_id)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        instance = serializer.save()
        invalidate_attribution_cache()
        return instance


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/reports/tracking/properties/<pk>/
    """
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Property.objects.select_related('publisher')
        if not self.request.user.is_admin_user:
            qs = qs.filter(publisher=self.request.user)
        return qs

    def perform_update(self, serializer):
        serializer.save()
        invalidate_attribution_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_attribution_cache()


# =============================================================================
# PLACEMENT VIEWS
# =============================================================================

class PlacementListCreateView(generics.ListCreateAPIView):
    serializer_class = PlacementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Placement.objects.select_related('property__publisher')
        if not self.request.user.is_admin_user:
            qs = qs.filter(property__publisher=self.request.user)

        property_id = self.request.query_params.get('property')
        if property_id:
            qs = qs.filter(property_id=property_id)

        property_pid = self.request.query_params.get('property_pid')
        if property_pid:
            qs = qs.filter(property__property_id=property_pid)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save()
        invalidate_attribution_cache()


class PlacementDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PlacementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Placement.objects.select_related('property__publisher')
        if not self.request.user.is_admin_user:
            qs = qs.filter(property__publisher=self.request.user)
        return qs

    def perform_update(self, serializer):
        serializer.save()
        invalidate_attribution_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_attribution_cache()


# =============================================================================
# GAM MAPPING VIEWS
# =============================================================================

class GAMMappingListCreateView(generics.ListCreateAPIView):
    serializer_class = GAMMappingSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = GAMMapping.objects.select_related('publisher', 'property', 'placement')
        publisher_id = self.request.query_params.get('publisher')
        if publisher_id:
            qs = qs.filter(publisher_id=publisher_id)
        source_type = self.request.query_params.get('source_type')
        if source_type:
            qs = qs.filter(source_type=source_type)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save()
        invalidate_attribution_cache()


class GAMMappingDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GAMMappingSerializer
    permission_classes = [IsAdminUser]
    queryset = GAMMapping.objects.all()

    def perform_update(self, serializer):
        serializer.save()
        invalidate_attribution_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_attribution_cache()


# =============================================================================
# SOURCE TYPE RULE VIEWS
# =============================================================================

class SourceTypeRuleListCreateView(generics.ListCreateAPIView):
    serializer_class = SourceTypeRuleSerializer
    permission_classes = [IsAdminUser]
    queryset = SourceTypeRule.objects.all().order_by('priority')


class SourceTypeRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SourceTypeRuleSerializer
    permission_classes = [IsAdminUser]
    queryset = SourceTypeRule.objects.all()

    def perform_update(self, serializer):
        serializer.save()
        invalidate_attribution_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_attribution_cache()


# =============================================================================
# TAG GENERATION VIEWS
# =============================================================================

class GenerateGPTTagView(APIView):
    """
    POST /api/reports/tracking/tags/gpt/
    Generate a standard GPT tag with hnt_* key-values.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TagGenerationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        d = serializer.validated_data
        result = generate_gpt_tag(
            network_code=d['network_code'],
            publisher_id=d['publisher_id'],
            property_id=d['property_id'],
            placement_id=d['placement_id'],
            placement_name=d['placement_name'],
            ad_size=d['ad_size'],
            source_type=d.get('source_type', 'mcm_direct'),
            env=d.get('env', 'web'),
            custom_ad_unit_path=d.get('custom_ad_unit_path'),
            div_id=d.get('div_id'),
            lazy_load=d.get('lazy_load', True),
            collapse_empty=d.get('collapse_empty', True),
        )
        return Response(result, status=status.HTTP_200_OK)


class GeneratePassbackTagView(APIView):
    """
    POST /api/reports/tracking/tags/passback/
    Generate a passback / fallback tag for GAM 360 demand.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PassbackTagSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        d = serializer.validated_data
        result = generate_passback_tag(
            network_code=d['network_code'],
            publisher_id=d['publisher_id'],
            property_id=d['property_id'],
            placement_id=d['placement_id'],
            placement_name=d['placement_name'],
            ad_size=d['ad_size'],
            source_type=d.get('source_type', 'gam360_passback'),
            env=d.get('env', 'web'),
            custom_ad_unit_path=d.get('custom_ad_unit_path'),
        )
        return Response(result, status=status.HTTP_200_OK)


class GenerateAdUnitPathView(APIView):
    """
    POST /api/reports/tracking/tags/ad-unit-path/
    Preview the structured ad unit path without generating a full tag.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        network_code = request.data.get('network_code')
        publisher_id = request.data.get('publisher_id')
        property_id = request.data.get('property_id')
        placement_name = request.data.get('placement_name', 'default')

        if not all([network_code, publisher_id, property_id]):
            return Response(
                {'error': 'network_code, publisher_id, property_id are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        path = generate_ad_unit_path(network_code, publisher_id, property_id, placement_name)
        return Response({'ad_unit_path': path}, status=status.HTTP_200_OK)


class AutoCreatePropertyPlacementsView(APIView):
    """
    POST /api/reports/tracking/auto-setup/
    Admin-only. For a given publisher, auto-create Property records from their
    Site objects and optionally seed default placements.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from accounts.models import User, Site

        publisher_id = request.data.get('publisher_id')
        if not publisher_id:
            return Response({'error': 'publisher_id is required'}, status=400)

        try:
            publisher = User.objects.get(id=publisher_id, role='publisher')
        except User.DoesNotExist:
            return Response({'error': 'Publisher not found'}, status=404)

        sites = Site.objects.filter(publisher=publisher)
        created_properties = 0
        created_placements = 0

        for site in sites:
            from urllib.parse import urlparse
            parsed = urlparse(site.url) if '://' in site.url else urlparse(f'https://{site.url}')
            domain = (parsed.netloc or parsed.path.split('/')[0]).strip().rstrip('/')
            if domain.startswith('www.'):
                domain = domain[4:]
            if not domain:
                continue

            slug = domain.replace('.', '_')
            prop_id = f"prop_{publisher.id}_{slug}"

            prop, prop_created = Property.objects.get_or_create(
                property_id=prop_id,
                defaults={
                    'publisher': publisher,
                    'domain': domain,
                    'platform': 'web',
                    'status': 'active',
                },
            )
            if prop_created:
                created_properties += 1

            default_sizes = request.data.get('default_sizes', ['300x250', '728x90', '320x50'])
            for size in default_sizes:
                plc_name = f"{slug}_{size.replace('x', 'x')}"
                plc_id = f"plc_{publisher.id}_{plc_name}"
                _, plc_created = Placement.objects.get_or_create(
                    placement_id=plc_id,
                    defaults={
                        'property': prop,
                        'placement_name': f"{domain} {size}",
                        'ad_size': size,
                        'status': 'active',
                    },
                )
                if plc_created:
                    created_placements += 1

        invalidate_attribution_cache()

        return Response({
            'success': True,
            'publisher': publisher.email,
            'created_properties': created_properties,
            'created_placements': created_placements,
        })
