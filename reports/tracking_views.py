# reports/tracking_views.py
#
# API views for unified tracking: Property, Placement, GAMMapping CRUD
# and tag generation endpoints.

import logging
from django.db import models
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
from .gam_client import GAMClientService
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
            domain=d.get('domain'),
            slot_name=d.get('slot_name'),
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
            domain=d.get('domain'),
            slot_name=d.get('slot_name'),
        )
        return Response(result, status=status.HTTP_200_OK)


class GenerateAdUnitPathView(APIView):
    """
    POST /api/reports/tracking/tags/ad-unit-path/
    Preview the ad unit path: /{network_code}/{domain}/{slot_name}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        network_code = request.data.get('network_code')
        domain = request.data.get('domain')
        slot_name = request.data.get('slot_name', 'Top_Leaderboard_ATF')

        if not all([network_code, domain]):
            return Response(
                {'error': 'network_code and domain are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        path = generate_ad_unit_path(network_code, domain, slot_name)
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


class CreateGAMAdUnitHierarchyView(APIView):
    """
    POST /api/reports/tracking/gam-ad-units/
    Admin-only. Creates the HnT ad unit hierarchy in GAM via InventoryService.

    Hierarchy:  root -> {domain} -> pub_{id} -> {property_id} -> {SlotName}
    Example:    /{networkCode}/example.com/pub_42/prop_42_example_com/Top_Leaderboard_ATF

    Body:
        {
            "publisher_id": 42,                          # required
            "domain": "example.com",                     # required
            "property_id": "prop_42_example_com",        # optional — adds prop level + GAM mappings
            "network_code": "23341212234",               # optional, auto-detected
            "gam_type": "o_and_o",                       # optional, auto-detected
            "use_templates": true,                       # default true — standard HnT slots
            "custom_units": [...],                       # optional extra units
            "parent_ad_unit_id": "12345",                # optional — override domain parent
            "create_gam_mappings": true                  # optional, default true
        }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        from accounts.models import User
        from decouple import config as decouple_config

        publisher_id = request.data.get('publisher_id')
        domain = request.data.get('domain', '').strip()

        if not publisher_id:
            return Response({'error': 'publisher_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not domain:
            return Response({'error': 'domain is required (e.g. example.com)'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            publisher = User.objects.get(id=publisher_id, role='publisher')
        except User.DoesNotExist:
            return Response({'error': 'Publisher not found'}, status=status.HTTP_404_NOT_FOUND)

        # Normalize domain
        if domain.startswith(('http://', 'https://')):
            from urllib.parse import urlparse
            domain = urlparse(domain).netloc or domain
        if domain.startswith('www.'):
            domain = domain[4:]
        domain = domain.rstrip('/')

        # Determine GAM network code and type
        gam_type = request.data.get('gam_type') or getattr(publisher, 'gam_type', 'mcm') or 'mcm'
        if gam_type == 'o_and_o':
            network_code = request.data.get('network_code') or decouple_config('GAM_OO_NETWORK_CODE', default='23341212234')
        else:
            network_code = request.data.get('network_code') or decouple_config('GAM_PARENT_NETWORK_CODE', default='23310681755')

        use_templates = request.data.get('use_templates', True)
        custom_units = request.data.get('custom_units')
        parent_ad_unit_id = request.data.get('parent_ad_unit_id')
        property_pid = request.data.get('property_id')

        # Resolve property from DB if provided
        prop = None
        if property_pid:
            try:
                prop = Property.objects.get(property_id=property_pid)
            except Property.DoesNotExist:
                try:
                    prop = Property.objects.get(pk=int(property_pid))
                except (Property.DoesNotExist, ValueError, TypeError):
                    prop = None

        result = GAMClientService.create_ad_unit_hierarchy(
            network_code=network_code,
            domain=domain,
            gam_type=gam_type,
            publisher_id=publisher_id,
            property_id=prop.property_id if prop else property_pid,
            use_templates=use_templates,
            custom_units=custom_units,
            parent_ad_unit_id=parent_ad_unit_id,
        )

        if not result.get('success'):
            return Response({
                'success': False,
                'error': result.get('error', 'Unknown error'),
                'created_units': result.get('created_units', []),
                'errors': result.get('errors', []),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Create GAMMapping records for slot-level units
        create_mappings = request.data.get('create_gam_mappings', True)
        mappings_created = 0
        if create_mappings:
            for unit_info in result.get('created_units', []):
                if unit_info.get('level') != 'slot':
                    continue
                ad_unit_path = unit_info.get('ad_unit_path', '')
                ad_unit_id = unit_info.get('id', '')
                slot_name = unit_info.get('name', '')

                matched_placement = None
                if prop:
                    matched_placement = (
                        Placement.objects.filter(property=prop)
                        .filter(models.Q(placement_name__icontains=slot_name))
                        .first()
                    )

                _, mapping_created = GAMMapping.objects.update_or_create(
                    gam_network_code=network_code,
                    gam_ad_unit_path=ad_unit_path,
                    defaults={
                        'publisher': publisher,
                        'property': prop,
                        'placement': matched_placement,
                        'gam_ad_unit_id': ad_unit_id,
                        'source_type': 'gam360_passback' if gam_type == 'o_and_o' else 'mcm_direct',
                        'is_active': True,
                    },
                )
                if mapping_created:
                    mappings_created += 1

            invalidate_attribution_cache()

        return Response({
            'success': True,
            'network_code': network_code,
            'domain': domain,
            'gam_type': gam_type,
            'publisher': publisher.email,
            'created_units': result.get('created_units', []),
            'gam_mappings_created': mappings_created,
            'errors': result.get('errors', []),
        }, status=status.HTTP_200_OK)
