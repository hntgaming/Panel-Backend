# reports/attribution.py
#
# Unified Attribution Service
#
# Resolves publisher/property/placement identity from GAM report data using
# a priority chain:
#   1. placement_id from key-values (hnt_plc_id)
#   2. property_id from key-values (hnt_prop_id)
#   3. publisher_id from key-values (hnt_pub_id)
#   4. ad unit path parsing (/network/hnt/pub_{id}/prop_{id}/{placement})
#   5. GAMMapping table lookup (ad_unit_id, line_item_id, order_id)
#   6. domain matching against Property.domain
#   7. legacy child_network_code / site fallback
#   8. unattributed
#
# Source type classification uses SourceTypeRule table + naming heuristics.

import re
import logging
from functools import lru_cache
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes

# Precompiled patterns for ad unit path parsing
_AD_UNIT_PATH_RE = re.compile(
    r'/(?P<network>\d+)/hnt/pub_(?P<pub_id>\d+)/prop_(?P<prop_id>[^/]+)/(?P<placement>[^/]+)',
    re.IGNORECASE,
)

# Heuristic patterns for source type classification when SourceTypeRule table is empty
_SOURCE_HEURISTICS = [
    (re.compile(r'passback|pb_|_pb|fallback', re.I), 'gam360_passback'),
    (re.compile(r'prebid|hb_|header.?bid', re.I), 'prebid'),
    (re.compile(r'open.?bid|ob_|EB_', re.I), 'open_bidding'),
    (re.compile(r'house|psa|backfill', re.I), 'house'),
    (re.compile(r'direct|io_|insertion', re.I), 'direct_campaign'),
    (re.compile(r'adx|ad.?exchange', re.I), 'adx_direct'),
]


def _get_property_domain_map():
    """Cached map of domain -> (property_id, publisher_id)."""
    key = 'attribution:domain_map'
    result = cache.get(key)
    if result is not None:
        return result

    from .models import Property
    result = {}
    for p in Property.objects.filter(status='active').select_related('publisher'):
        domain = p.domain.lower().strip().rstrip('/')
        if domain:
            result[domain] = {
                'property_id': p.property_id,
                'publisher_id': p.publisher_id,
            }
            if domain.startswith('www.'):
                result[domain[4:]] = result[domain]

    cache.set(key, result, CACHE_TTL)
    return result


def _get_ad_unit_mapping_map():
    """Cached map of gam_ad_unit_path -> mapping dict."""
    key = 'attribution:au_map'
    result = cache.get(key)
    if result is not None:
        return result

    from .models import GAMMapping
    result = {}
    for m in GAMMapping.objects.filter(is_active=True).select_related('property', 'placement'):
        if m.gam_ad_unit_path:
            result[m.gam_ad_unit_path] = {
                'publisher_id': m.publisher_id,
                'property_id': m.property.property_id if m.property else None,
                'placement_id': m.placement.placement_id if m.placement else None,
                'source_type': m.source_type,
            }
        if m.gam_ad_unit_id:
            result[f'__auid__{m.gam_ad_unit_id}'] = result.get(m.gam_ad_unit_path, {
                'publisher_id': m.publisher_id,
                'property_id': m.property.property_id if m.property else None,
                'placement_id': m.placement.placement_id if m.placement else None,
                'source_type': m.source_type,
            })

    cache.set(key, result, CACHE_TTL)
    return result


def _get_source_type_rules():
    """Cached ordered list of SourceTypeRule entries."""
    key = 'attribution:source_rules'
    result = cache.get(key)
    if result is not None:
        return result

    from .models import SourceTypeRule
    result = list(
        SourceTypeRule.objects.filter(is_active=True)
        .order_by('priority')
        .values('match_field', 'match_type', 'match_value', 'source_type')
    )
    cache.set(key, result, CACHE_TTL)
    return result


def invalidate_attribution_cache():
    """Call after Property, Placement, GAMMapping, or SourceTypeRule changes."""
    for key in ('attribution:domain_map', 'attribution:au_map', 'attribution:source_rules'):
        cache.delete(key)


class AttributionResult:
    __slots__ = (
        'publisher_id', 'property_id', 'placement_id',
        'source_type', 'method',
    )

    def __init__(self):
        self.publisher_id = None
        self.property_id = None
        self.placement_id = None
        self.source_type = None
        self.method = 'unattributed'

    def is_resolved(self):
        return self.publisher_id is not None

    def to_dict(self):
        return {
            'publisher_id': self.publisher_id,
            'property_id_tracking': self.property_id,
            'placement_id_tracking': self.placement_id,
            'source_type': self.source_type,
            'attribution_method': self.method,
        }


def resolve_attribution(row_data, invitation=None):
    """
    Resolve attribution for a single report row.

    Parameters
    ----------
    row_data : dict
        Raw row from GAM report CSV (header-keyed).
        May contain: AD_UNIT_NAME, AD_UNIT_ID, SITE_NAME, CUSTOM_TARGETING_VALUE_ID,
        LINE_ITEM_NAME, ORDER_NAME, etc.
    invitation : object, optional
        The invitation/context object from the report service with child_network_code,
        publisher_id, gam_type, etc.

    Returns
    -------
    AttributionResult
    """
    result = AttributionResult()

    # Step 1-3: Key-value extraction (hnt_pub_id, hnt_prop_id, hnt_plc_id)
    _resolve_from_key_values(row_data, result)
    if result.placement_id:
        result.method = 'key_value'
        _classify_source_type(row_data, result, invitation)
        return result

    # Step 4: Ad unit path parsing
    ad_unit_name = str(row_data.get('AD_UNIT_NAME', '') or '')
    if ad_unit_name:
        _resolve_from_ad_unit_path(ad_unit_name, result)
        if result.is_resolved():
            result.method = 'ad_unit_path'
            _classify_source_type(row_data, result, invitation)
            return result

    # Step 5: GAM mapping table
    ad_unit_id = str(row_data.get('AD_UNIT_ID', '') or '')
    _resolve_from_gam_mappings(ad_unit_name, ad_unit_id, result)
    if result.is_resolved():
        result.method = 'gam_mapping'
        _classify_source_type(row_data, result, invitation)
        return result

    # Step 6: Domain matching
    site_name = str(row_data.get('SITE_NAME', '') or '').lower().strip()
    if site_name and site_name not in ('safeframe.googlesyndication.com', 'total', 'totals', ''):
        _resolve_from_domain(site_name, result)
        if result.is_resolved():
            result.method = 'domain_match'
            _classify_source_type(row_data, result, invitation)
            return result

    # Step 7: Legacy fallback from invitation context
    if invitation:
        result.publisher_id = getattr(invitation, 'publisher_id', None)
        gam_type = getattr(invitation, 'gam_type', None)
        if gam_type == 'o_and_o':
            site_domain = getattr(invitation, 'site_domain', '')
            if site_domain:
                _resolve_from_domain(site_domain, result)
        result.method = 'legacy'
        _classify_source_type(row_data, result, invitation)
        return result

    # Step 8: Unattributed
    result.method = 'unattributed'
    return result


def _resolve_from_key_values(row_data, result):
    """Extract hnt_* key-values from GAM report custom targeting columns."""
    for key in ('hnt_pub_id', 'hnt_prop_id', 'hnt_plc_id'):
        val = row_data.get(key) or row_data.get(key.upper())
        if val:
            val = str(val).strip()
            if key == 'hnt_pub_id':
                try:
                    result.publisher_id = int(val)
                except (ValueError, TypeError):
                    pass
            elif key == 'hnt_prop_id':
                result.property_id = val
            elif key == 'hnt_plc_id':
                result.placement_id = val

    source = row_data.get('hnt_source') or row_data.get('HNT_SOURCE')
    if source:
        result.source_type = str(source).strip()


def _resolve_from_ad_unit_path(ad_unit_name, result):
    """Parse structured ad unit path: /network/hnt/pub_{id}/prop_{id}/{placement}"""
    match = _AD_UNIT_PATH_RE.search(ad_unit_name)
    if match:
        try:
            result.publisher_id = int(match.group('pub_id'))
        except (ValueError, TypeError):
            pass
        result.property_id = match.group('prop_id')
        result.placement_id = match.group('placement')
        return

    # Fallback: look up from mapping table by ad unit path
    au_map = _get_ad_unit_mapping_map()
    mapping = au_map.get(ad_unit_name)
    if mapping:
        result.publisher_id = mapping.get('publisher_id')
        result.property_id = mapping.get('property_id')
        result.placement_id = mapping.get('placement_id')


def _resolve_from_gam_mappings(ad_unit_name, ad_unit_id, result):
    """Look up GAM mapping by ad unit path or ID."""
    au_map = _get_ad_unit_mapping_map()

    mapping = None
    if ad_unit_name:
        mapping = au_map.get(ad_unit_name)
    if not mapping and ad_unit_id:
        mapping = au_map.get(f'__auid__{ad_unit_id}')

    if mapping:
        result.publisher_id = mapping.get('publisher_id')
        result.property_id = mapping.get('property_id')
        result.placement_id = mapping.get('placement_id')
        if mapping.get('source_type') and mapping['source_type'] != 'unknown':
            result.source_type = mapping['source_type']


def _resolve_from_domain(domain, result):
    """Match a domain (or subdomain) against known properties."""
    domain = domain.lower().strip().rstrip('/')
    if domain.startswith('www.'):
        domain = domain[4:]

    domain_map = _get_property_domain_map()

    if domain in domain_map:
        entry = domain_map[domain]
        result.publisher_id = entry['publisher_id']
        result.property_id = entry['property_id']
        return

    # Try stripping subdomains progressively: sub.example.com -> example.com
    parts = domain.split('.')
    for i in range(1, len(parts) - 1):
        parent = '.'.join(parts[i:])
        if parent in domain_map:
            entry = domain_map[parent]
            result.publisher_id = entry['publisher_id']
            result.property_id = entry['property_id']
            return


def _classify_source_type(row_data, result, invitation=None):
    """Classify the demand source type if not already set."""
    if result.source_type and result.source_type != 'unknown':
        return

    # Try SourceTypeRule table first
    rules = _get_source_type_rules()
    test_fields = {
        'line_item_name': str(row_data.get('LINE_ITEM_NAME', '') or ''),
        'line_item_id': str(row_data.get('LINE_ITEM_ID', '') or ''),
        'order_name': str(row_data.get('ORDER_NAME', '') or ''),
        'order_id': str(row_data.get('ORDER_ID', '') or ''),
        'ad_unit_path': str(row_data.get('AD_UNIT_NAME', '') or ''),
        'creative_name': str(row_data.get('CREATIVE_NAME', '') or ''),
    }

    for rule in rules:
        field_val = test_fields.get(rule['match_field'], '')
        if not field_val:
            continue
        match_val = rule['match_value']
        matched = False

        if rule['match_type'] == 'contains':
            matched = match_val.lower() in field_val.lower()
        elif rule['match_type'] == 'startswith':
            matched = field_val.lower().startswith(match_val.lower())
        elif rule['match_type'] == 'exact':
            matched = field_val == match_val
        elif rule['match_type'] == 'regex':
            try:
                matched = bool(re.search(match_val, field_val, re.IGNORECASE))
            except re.error:
                pass

        if matched:
            result.source_type = rule['source_type']
            return

    # Heuristic fallback
    combined = ' '.join(v for v in test_fields.values() if v)
    if combined:
        for pattern, src_type in _SOURCE_HEURISTICS:
            if pattern.search(combined):
                result.source_type = src_type
                return

    # Default based on invitation gam_type
    if invitation:
        gam_type = getattr(invitation, 'gam_type', None)
        if gam_type == 'o_and_o':
            result.source_type = 'gam360_passback'
        elif gam_type == 'mcm':
            result.source_type = 'mcm_direct'
        else:
            result.source_type = 'unknown'
    else:
        result.source_type = 'unknown'


def batch_resolve(records, invitation=None):
    """
    Resolve attribution for a batch of record dicts (post-processing).
    Mutates each record dict in-place by adding tracking fields.
    Returns the same list.
    """
    for record in records:
        attr = resolve_attribution(record, invitation)
        record.update(attr.to_dict())
        # Preserve existing publisher_id from invitation if attribution didn't find one
        if not record.get('publisher_id') and invitation:
            record['publisher_id'] = getattr(invitation, 'publisher_id', None)
    return records
