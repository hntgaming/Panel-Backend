# reports/services.py - High-Performance GAM Report Fetcher
#
# Optimizations applied from GAM-Sentinel architecture:
#   1. Parallel dimension processing per account (ThreadPoolExecutor)
#   2. Bulk DB writes (bulk_create + bulk_update) instead of per-record update_or_create
#   3. GAM client caching (shared across publishers of the same GAM type)
#   4. Metric fallback (retry without TOTAL_AD_REQUESTS on unsupported dimensions)
#   5. Bypasses model.full_clean() during bulk inserts for speed

import logging
import tempfile
import gzip
import os
import csv
import io
import time
import concurrent.futures
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.db import transaction, connection
from django.db.models import Q
from django.conf import settings
from googleads import ad_manager
from googleads import errors as gam_errors

from .gam_client import GAMClientService
from accounts.models import User
from .models import MasterMetaData, ReportSyncLog
from .constants import dimension_map, metrics, dimension_metrics

logger = logging.getLogger(__name__)

DIMENSION_WORKERS = 8
BATCH_SIZE = 1000
MAX_RETRIES = 3
RETRY_DELAY = 5
QUOTA_RETRY_DELAY = 5
MAX_QUOTA_RETRIES = 5

AUTH_ERROR_KEYWORDS = [
    'AuthenticationError.NO_NETWORKS_TO_ACCESS',
    'NO_NETWORKS_TO_ACCESS',
    'AuthenticationError',
    'authentication',
    'unauthorized',
    'forbidden',
    'invalid credentials',
    'access denied',
]


def _is_auth_error(message: str) -> bool:
    msg_lower = message.lower()
    return any(kw.lower() in msg_lower for kw in AUTH_ERROR_KEYWORDS)


def _safe_int(value) -> int:
    try:
        return int(float(value)) if value else 0
    except (ValueError, TypeError):
        return 0


def _micros_to_currency(value) -> Decimal:
    try:
        if value is None or value == "":
            return Decimal('0')
        return Decimal(str(value)) / Decimal('1000000')
    except (ValueError, TypeError):
        return Decimal('0')


def _decimal_to_pct(value) -> Decimal:
    try:
        if value:
            return Decimal(str(value)) * 100
        return Decimal('0')
    except (ValueError, TypeError):
        return Decimal('0')


def _quantize(value: Decimal, places: int) -> Decimal:
    q = Decimal('1').scaleb(-places)
    try:
        return (value if isinstance(value, Decimal) else Decimal(str(value or '0'))).quantize(q, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0').quantize(q, rounding=ROUND_HALF_UP)


def _aggregate_oo_records(records):
    """
    For O&O publishers, SITE_NAME is added as an extra dimension to all reports.
    GAM then breaks down rows per subdomain (e.g. ldr.virviral.xyz,
    nya.virviral.xyz), creating duplicate dimension_value keys like "Chrome"
    appearing multiple times. This function sums the additive metrics
    (impressions, revenue, clicks, ad_requests) and recalculates the derived
    ones (eCPM, CTR, fill_rate, viewability) from the aggregated totals.
    """
    if not records:
        return records

    from collections import defaultdict
    buckets = defaultdict(lambda: {
        'impressions': 0,
        'revenue': Decimal('0'),
        'clicks': 0,
        'total_ad_requests': 0,
        'viewable_weighted': Decimal('0'),
    })

    templates = {}

    for r in records:
        key = (r['child_network_code'], r['date'], r['dimension_type'], r['dimension_value'])
        b = buckets[key]
        imp = r['impressions']
        b['impressions'] += imp
        b['revenue'] += r['revenue']
        b['clicks'] += r['clicks']
        b['total_ad_requests'] += r['total_ad_requests']
        b['viewable_weighted'] += r['viewable_impressions_rate'] * imp
        if key not in templates:
            templates[key] = r

    aggregated = []
    for key, b in buckets.items():
        tmpl = dict(templates[key])
        imp = b['impressions']
        rev = b['revenue']
        clicks = b['clicks']
        ad_req = b['total_ad_requests']

        ecpm = (rev / imp * 1000) if imp > 0 else Decimal('0')
        ctr = (Decimal(clicks) / Decimal(imp) * 100) if imp > 0 else Decimal('0')
        view_rate = (b['viewable_weighted'] / imp) if imp > 0 else Decimal('0')

        tmpl['impressions'] = imp
        tmpl['revenue'] = _quantize(rev, 2)
        tmpl['clicks'] = clicks
        tmpl['total_ad_requests'] = ad_req
        tmpl['ecpm'] = _quantize(ecpm, 2)
        tmpl['ctr'] = _quantize(ctr, 2)
        tmpl['viewable_impressions_rate'] = _quantize(view_rate, 2)
        aggregated.append(tmpl)

    return aggregated


class GAMReportService:
    """
    High-performance service for fetching GAM reports.
    Parallelises at both account level (management command) and dimension level
    (within each account) for maximum throughput.
    """

    DIMENSION_MAP = dimension_map
    METRICS = metrics

    # ------------------------------------------------------------------
    # Entry point for cron / management command
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_gam_reports(date_from=None, date_to=None, triggered_by=None):
        if not date_from:
            date_to = timezone.now().date()
            date_from = date_to - timedelta(days=4)
        if not date_to:
            date_to = timezone.now().date()

        sync_id = f"sync_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        sync_log = ReportSyncLog.objects.create(
            sync_id=sync_id,
            date_from=date_from,
            date_to=date_to,
            triggered_by=triggered_by,
            is_manual=triggered_by is not None,
        )

        logger.info(f"Starting GAM report sync {sync_id} for {date_from} to {date_to}")

        try:
            from core.models import StatusChoices
            from itertools import chain

            mcm_publishers = User.objects.filter(
                role=User.UserRole.PUBLISHER,
                status=StatusChoices.ACTIVE,
                gam_type='mcm',
                network_id__isnull=False,
            ).exclude(network_id='')

            oo_publishers = User.objects.filter(
                role=User.UserRole.PUBLISHER,
                status=StatusChoices.ACTIVE,
                gam_type='o_and_o',
            ).filter(
                Q(site_url__isnull=False) & ~Q(site_url='') | Q(sites__isnull=False)
            ).distinct()

            eligible_publishers = list(chain(mcm_publishers, oo_publishers))

            successful_count = 0
            failed_count = 0
            total_records_created = 0
            total_records_updated = 0

            for publisher in eligible_publishers:
                try:
                    result = GAMReportService._process_publisher_network(
                        publisher, date_from, date_to
                    )
                    successful_count += 1
                    total_records_created += result.get('records_created', 0)
                    total_records_updated += result.get('records_updated', 0)
                except Exception as e:
                    failed_count += 1
                    label = publisher.network_id or publisher.site_url or publisher.email
                    logger.error(f"Failed to process publisher {label}: {e}")
                    sync_log.add_network_error(label or 'unknown', str(e))

            sync_log.mark_completed(successful_count, failed_count, total_records_created, total_records_updated)
            logger.info(f"Sync {sync_id} completed: {successful_count} success, {failed_count} failed")

            return {
                'success': True,
                'sync_id': sync_id,
                'successful_networks': successful_count,
                'failed_networks': failed_count,
                'total_records_created': total_records_created,
                'total_records_updated': total_records_updated,
            }

        except Exception as e:
            logger.error(f"Critical error in sync {sync_id}: {e}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = timezone.now()
            sync_log.save()
            return {'success': False, 'sync_id': sync_id, 'error': str(e)}

    # ------------------------------------------------------------------
    # Publisher routing
    # ------------------------------------------------------------------
    @staticmethod
    def _process_publisher_network(publisher, date_from, date_to):
        gam_type = getattr(publisher, 'gam_type', 'mcm') or 'mcm'
        if gam_type == 'o_and_o':
            return GAMReportService._process_oo_publisher(publisher, date_from, date_to)
        return GAMReportService._process_mcm_publisher(publisher, date_from, date_to)

    # ------------------------------------------------------------------
    # MCM publisher
    # ------------------------------------------------------------------
    @staticmethod
    def _process_mcm_publisher(publisher, date_from, date_to):
        child_network_code = publisher.network_id
        from decouple import config as decouple_config
        yaml_network_code = decouple_config('GAM_PARENT_NETWORK_CODE', default='23310681755')

        try:
            client = GAMClientService.get_googleads_client(yaml_network_code, gam_type='mcm')
        except Exception as e:
            if _is_auth_error(str(e)):
                return {'records_created': 0, 'records_updated': 0, 'status': 'skipped'}
            raise

        class _Invitation:
            def __init__(self):
                self.child_network_code = child_network_code
                self.delegation_type = 'MANAGE_INVENTORY'
                self.gam_type = 'mcm'
                self.parent_network = type('P', (), {'network_code': yaml_network_code, 'network_name': 'Parent Network'})()
                self.publisher_name = publisher.company_name or publisher.email
                self.publisher_id = publisher.id

        return GAMReportService._fetch_all_dimensions_parallel(
            client, _Invitation(), date_from, date_to
        )

    # ------------------------------------------------------------------
    # O&O publisher
    # ------------------------------------------------------------------
    @staticmethod
    def _process_oo_publisher(publisher, date_from, date_to):
        from urllib.parse import urlparse
        from decouple import config as decouple_config
        from accounts.models import Site

        oo_network_code = decouple_config('GAM_OO_NETWORK_CODE', default='23341212234')

        try:
            client = GAMClientService.get_googleads_client(oo_network_code, gam_type='o_and_o')
        except Exception as e:
            if _is_auth_error(str(e)):
                return {'records_created': 0, 'records_updated': 0, 'status': 'skipped'}
            raise

        def _url_to_domain(url):
            parsed = urlparse(url) if '://' in url else urlparse(f'https://{url}')
            d = parsed.netloc or parsed.path.split('/')[0]
            if d.startswith('www.'):
                d = d[4:]
            return d.rstrip('/').split(':')[0]

        site_urls = list(
            Site.objects.filter(publisher=publisher)
            .values_list('url', flat=True)
        )
        if not site_urls and publisher.site_url:
            site_urls = [publisher.site_url]
        if not site_urls:
            return {'records_created': 0, 'records_updated': 0, 'status': 'skipped'}

        total_created = 0
        total_updated = 0

        for url in site_urls:
            domain = _url_to_domain(url)
            if not domain:
                continue

            class _OOInvitation:
                def __init__(self, _domain):
                    self.child_network_code = _domain
                    self.delegation_type = 'OWNED_AND_OPERATED'
                    self.gam_type = 'o_and_o'
                    self.site_domain = _domain
                    self.parent_network = type('P', (), {'network_code': oo_network_code, 'network_name': 'O&O Network'})()
                    self.publisher_name = publisher.company_name or publisher.email
                    self.publisher_id = publisher.id

            result = GAMReportService._fetch_all_dimensions_parallel(
                client, _OOInvitation(domain), date_from, date_to
            )
            total_created += result.get('records_created', 0)
            total_updated += result.get('records_updated', 0)

        return {'records_created': total_created, 'records_updated': total_updated}

    # ------------------------------------------------------------------
    # CORE OPTIMIZATION: Parallel dimension fetching
    # ------------------------------------------------------------------
    @staticmethod
    def _fetch_all_dimensions_parallel(client, invitation, date_from, date_to):
        """
        Fetch all 8 dimension reports concurrently using a thread pool.
        Each date in the range is fetched individually to prevent GAM from
        aggregating multi-day data into a single row (non-DATE dimensions
        don't break down by date).
        """
        from datetime import timedelta

        dimension_keys = list(dimension_map.keys())
        all_records = []
        auth_failed = False

        dates = []
        d = date_from
        while d <= date_to:
            dates.append(d)
            d += timedelta(days=1)

        tasks = [(dk, single_date) for single_date in dates for dk in dimension_keys]

        def _fetch_dim(dim_key, target_date):
            return dim_key, target_date, GAMReportService._fetch_dimension_with_fallback(
                client, invitation, dim_key, target_date, target_date
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=DIMENSION_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_dim, dk, td): (dk, td)
                for dk, td in tasks
            }

            for future in concurrent.futures.as_completed(futures):
                dk, td = futures[future]
                try:
                    _, _, result = future.result()
                    if result.get('skipped_due_to_auth_error'):
                        auth_failed = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    all_records.extend(result.get('records', []))
                except Exception as e:
                    if _is_auth_error(str(e)):
                        auth_failed = True
                        break
                    logger.warning(f"Dimension {dk} ({td}) failed for {invitation.child_network_code}: {e}")

        if auth_failed:
            return {'records_created': 0, 'records_updated': 0, 'status': 'auth_error'}

        created, updated = GAMReportService._bulk_upsert_records(all_records)

        return {'records_created': created, 'records_updated': updated}

    # ------------------------------------------------------------------
    # Single dimension fetch with metric fallback
    # ------------------------------------------------------------------
    @staticmethod
    def _fetch_dimension_with_fallback(client, invitation, dimension_key, date_from, date_to):
        """
        Fetch a single dimension report. If the primary metric set fails
        (e.g. TOTAL_AD_REQUESTS not supported), retry with a fallback set.
        """
        dim_metrics = list(dimension_metrics.get(dimension_key, metrics))

        metric_variants = [dim_metrics]
        fallback = [m for m in dim_metrics if m != 'TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS']
        if len(fallback) < len(dim_metrics):
            metric_variants.append(fallback)

        last_error = None
        for variant in metric_variants:
            try:
                return GAMReportService._fetch_single_dimension(
                    client, invitation, dimension_key, variant, date_from, date_to
                )
            except Exception as e:
                last_error = e
                if _is_auth_error(str(e)):
                    return {'skipped_due_to_auth_error': True, 'records': []}
                logger.debug(f"Metric variant failed for {dimension_key}, trying fallback: {e}")

        raise last_error

    @staticmethod
    def _fetch_single_dimension(client, invitation, dimension_key, metrics_list, date_from, date_to):
        """
        Execute a single GAM report query, download gzipped CSV, parse rows.
        """
        dimensions = list(GAMReportService.DIMENSION_MAP.get(dimension_key, []))
        filter_statement = None

        is_oo = (
            getattr(invitation, 'gam_type', None) == 'o_and_o'
            or invitation.delegation_type == 'OWNED_AND_OPERATED'
        )

        if is_oo:
            if "SITE_NAME" not in dimensions:
                dimensions.append("SITE_NAME")
        elif invitation.delegation_type == 'MANAGE_INVENTORY':
            if "CHILD_NETWORK_CODE" not in dimensions:
                dimensions.append("CHILD_NETWORK_CODE")
            filter_statement = {
                'query': 'WHERE CHILD_NETWORK_CODE = :childNetworkCode',
                'values': [{
                    'key': 'childNetworkCode',
                    'value': {'xsi_type': 'TextValue', 'value': str(invitation.child_network_code)},
                }],
            }

        report_query = {
            "dimensions": dimensions,
            "columns": metrics_list,
            "dateRangeType": "CUSTOM_DATE",
            "startDate": date_from,
            "endDate": date_to,
            "reportCurrency": "USD",
        }
        if "AD_UNIT_NAME" in dimensions:
            report_query["adUnitView"] = "FLAT"
        if filter_statement:
            report_query["statement"] = filter_statement

        report_job = {"reportQuery": report_query}

        try:
            report_downloader = client.GetDataDownloader(version="v202508")
            report_job_id = report_downloader.WaitForReport(report_job)
        except Exception as e:
            if _is_auth_error(str(e)):
                return {'skipped_due_to_auth_error': True, 'records': []}
            raise

        with tempfile.TemporaryFile() as fp:
            report_downloader.DownloadReportToFile(report_job_id, 'GZIPPED_CSV', fp, include_totals_row=True)
            fp.seek(0)
            decompressed = gzip.decompress(fp.read()).decode('utf-8', errors='ignore')

        reader = csv.reader(io.StringIO(decompressed))
        rows = list(reader)

        if len(rows) <= 1:
            return {'records': []}

        headers = [col.replace('Dimension.', '').replace('Column.', '') for col in rows[0]]

        records = GAMReportService._process_report_rows(
            headers, rows[1:], invitation, dimension_key, date_from
        )
        return {'records': records}

    # ------------------------------------------------------------------
    # CSV row processing
    # ------------------------------------------------------------------
    @staticmethod
    def _process_report_rows(headers, data_rows, invitation, dimension_key, date_from):
        from decouple import config as decouple_config

        is_oo = (
            getattr(invitation, 'gam_type', None) == 'o_and_o'
            or invitation.delegation_type == 'OWNED_AND_OPERATED'
        )
        oo_domain = getattr(invitation, 'site_domain', '').lower().strip() if is_oo else ''

        if is_oo:
            parent_network_code = decouple_config('GAM_OO_NETWORK_CODE', default='23341212234')
        else:
            parent_network_code = decouple_config('GAM_PARENT_NETWORK_CODE', default='23310681755')

        skip_dims = (
            'SITE_NAME', 'AD_UNIT_NAME', 'MOBILE_APP_NAME',
            'DEVICE_CATEGORY_NAME', 'COUNTRY_NAME',
            'MOBILE_CARRIER_NAME', 'CARRIER_NAME', 'BROWSER_NAME',
            'INVENTORY_FORMAT', 'INVENTORY_FORMAT_NAME',
        )
        dim_cols = GAMReportService.DIMENSION_MAP.get(dimension_key, [])

        records = []
        for row_data in data_rows:
            try:
                row = dict(zip(headers, row_data))

                skip = False
                for dc in skip_dims:
                    if dc in row:
                        val = str(row.get(dc) or '').strip().lower()
                        if val in ('total', 'totals', ''):
                            skip = True
                            break
                if skip:
                    continue

                if is_oo and oo_domain:
                    row_site = str(row.get('SITE_NAME', '')).lower().strip()
                    if not row_site or oo_domain not in row_site:
                        continue

                if dim_cols:
                    dimension_value = " | ".join(str(row.get(c, 'All')) for c in dim_cols)
                else:
                    dimension_value = 'All'

                if dimension_key == 'overview' and hasattr(invitation, 'publisher_name'):
                    dimension_value = invitation.publisher_name

                impressions = _safe_int(row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS', 0))
                revenue = _micros_to_currency(row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE', 0))
                clicks = _safe_int(row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS', 0))
                total_ad_requests = _safe_int(row.get('TOTAL_AD_REQUESTS', 0))
                total_ad_requests += _safe_int(row.get('TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS', 0))

                api_ecpm = row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_AVERAGE_ECPM', 0)
                api_ctr = row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_CTR', 0)

                ecpm = _micros_to_currency(api_ecpm) if api_ecpm else Decimal('0')
                ctr = _decimal_to_pct(api_ctr) if api_ctr else Decimal('0')

                if ecpm == 0 and impressions > 0:
                    ecpm = (revenue / impressions) * 1000
                if ctr == 0 and impressions > 0:
                    ctr = (Decimal(clicks) / Decimal(impressions)) * 100

                fill_rate = Decimal('0')
                if total_ad_requests > 0:
                    fill_rate = (Decimal(impressions) / Decimal(total_ad_requests)) * 100

                viewable_rate = _decimal_to_pct(
                    row.get('AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE')
                )

                records.append({
                    'parent_network_code': parent_network_code,
                    'publisher_id': getattr(invitation, 'publisher_id', None),
                    'child_network_code': invitation.child_network_code,
                    'dimension_type': dimension_key,
                    'dimension_value': dimension_value,
                    'date': date_from,
                    'currency': 'USD',
                    'impressions': impressions,
                    'revenue': _quantize(revenue, 2),
                    'ecpm': _quantize(ecpm, 2),
                    'clicks': clicks,
                    'ctr': _quantize(ctr, 2),
                    'total_ad_requests': total_ad_requests,
                    'viewable_impressions_rate': _quantize(viewable_rate, 2),
                })
            except Exception as e:
                logger.warning(f"Row processing error: {e}")
                continue

        if is_oo and dimension_key != 'site':
            records = _aggregate_oo_records(records)

        return records

    # ------------------------------------------------------------------
    # CORE OPTIMIZATION: Bulk upsert
    # ------------------------------------------------------------------
    @staticmethod
    def _bulk_upsert_records(records_data):
        """
        Bulk insert/update records using Django's bulk_create with
        update_conflicts to avoid N+1 queries.  Falls back to batched
        update_or_create for databases that don't support ON CONFLICT.
        """
        if not records_data:
            return 0, 0

        created = 0
        updated = 0

        unique_fields = ['child_network_code', 'date', 'dimension_type', 'dimension_value']
        update_fields = [
            'parent_network_code', 'publisher_id', 'currency',
            'impressions', 'revenue', 'ecpm', 'clicks', 'ctr',
            'total_ad_requests', 'viewable_impressions_rate',
        ]

        for i in range(0, len(records_data), BATCH_SIZE):
            batch = records_data[i:i + BATCH_SIZE]
            objs = [
                MasterMetaData(
                    parent_network_code=r['parent_network_code'],
                    publisher_id=r.get('publisher_id'),
                    child_network_code=r['child_network_code'],
                    dimension_type=r['dimension_type'],
                    dimension_value=r['dimension_value'],
                    date=r['date'],
                    currency=r['currency'],
                    impressions=r['impressions'],
                    revenue=r['revenue'],
                    ecpm=r['ecpm'],
                    clicks=r['clicks'],
                    ctr=r['ctr'],
                    total_ad_requests=r.get('total_ad_requests', 0),
                    eligible_ad_requests=r.get('eligible_ad_requests', 0),
                    viewable_impressions_rate=r['viewable_impressions_rate'],
                )
                for r in batch
            ]

            try:
                result = MasterMetaData.objects.bulk_create(
                    objs,
                    update_conflicts=True,
                    unique_fields=unique_fields,
                    update_fields=update_fields,
                    batch_size=BATCH_SIZE,
                )
                created += len(result)
            except Exception:
                for r in batch:
                    try:
                        lookup = {f: r[f] for f in unique_fields}
                        defaults = {f: r[f] for f in update_fields if f in r}
                        defaults['eligible_ad_requests'] = r.get('eligible_ad_requests', 0)
                        _, was_created = MasterMetaData.objects.update_or_create(
                            **lookup, defaults=defaults,
                        )
                        if was_created:
                            created += 1
                        else:
                            updated += 1
                    except Exception as e:
                        logger.warning(f"Record upsert failed: {e}")

        return created, updated

    # ------------------------------------------------------------------
    # Legacy compatibility: _process_child_network (used nowhere now but kept for safety)
    # ------------------------------------------------------------------
    @staticmethod
    def _process_child_network(invitation, date_from, date_to):
        child_network_code = invitation.child_network_code
        try:
            client = GAMClientService.get_googleads_client(child_network_code, gam_type='mcm')
        except Exception as e:
            if _is_auth_error(str(e)):
                return {'records_created': 0, 'records_updated': 0, 'skipped_due_to_auth_error': True}
            raise

        return GAMReportService._fetch_all_dimensions_parallel(client, invitation, date_from, date_to)

    @staticmethod
    def _get_child_network_client(child_network_code, gam_type='mcm'):
        return GAMClientService.get_googleads_client(child_network_code, gam_type=gam_type)

    # ------------------------------------------------------------------
    # Kept for backward compatibility with bulk_create_or_update_records calls
    # ------------------------------------------------------------------
    @staticmethod
    def bulk_create_or_update_records(records_data):
        created, updated = GAMReportService._bulk_upsert_records(records_data)
        return {'created': created, 'updated': updated}

    @staticmethod
    def _store_report_data(data):
        try:
            lookup = {
                'child_network_code': data['child_network_code'],
                'dimension_type': data['dimension_type'],
                'date': data['date'],
            }
            if data['dimension_type'] != 'overview':
                lookup['dimension_value'] = data['dimension_value']
            lookup['parent_network_code'] = data['parent_network_code']

            defaults = {
                'publisher_id': data.get('publisher_id'),
                'dimension_value': data.get('dimension_value'),
                'currency': data['currency'],
                'impressions': data['impressions'],
                'revenue': data['revenue'],
                'ecpm': data['ecpm'],
                'clicks': data['clicks'],
                'ctr': data['ctr'],
                'total_ad_requests': data.get('total_ad_requests', 0),
                'eligible_ad_requests': data.get('eligible_ad_requests', 0),
                'viewable_impressions_rate': data['viewable_impressions_rate'],
            }
            _, was_created = MasterMetaData.objects.update_or_create(**lookup, defaults=defaults)
            return {'created': 1 if was_created else 0, 'updated': 0 if was_created else 1}
        except Exception as e:
            logger.error(f"Failed to store report data: {e}")
            return None

    # Kept for any external callers
    _fetch_child_dimension_reports = None  # Removed; use _fetch_single_dimension
    _process_report_data = None  # Removed; use _process_report_rows
