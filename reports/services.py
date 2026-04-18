# reports/services.py - High-Performance GAM Report Fetcher
#
# Each partner admin connects their own GAM account via GAMCredential.
# Reports are fetched directly from the partner's GAM network.
#
# Optimizations:
#   1. Parallel dimension processing per account (ThreadPoolExecutor)
#   2. Bulk DB writes (bulk_create + bulk_update) instead of per-record update_or_create
#   3. GAM client caching per partner
#   4. Metric fallback (retry without TOTAL_AD_REQUESTS on unsupported dimensions)
#   5. Bypasses model.full_clean() during bulk inserts for speed

import logging
import tempfile
import gzip
import os
import csv
import io
import time
import threading
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

_GAMCredential = None  # lazy import to avoid circular imports

def _get_gam_credential_model():
    global _GAMCredential
    if _GAMCredential is None:
        from accounts.models import GAMCredential
        _GAMCredential = GAMCredential
    return _GAMCredential

logger = logging.getLogger(__name__)

DIMENSION_WORKERS = 4
BATCH_SIZE = 1000
MAX_RETRIES = 3
RETRY_DELAY = 5
QUOTA_RETRY_DELAY = 10
MAX_QUOTA_RETRIES = 8

_api_lock = threading.Lock()
_MIN_REQUEST_INTERVAL = 0.15  # ~6-7 requests/sec across all threads
_last_request_time = 0.0


def _throttle():
    """Global rate limiter — ensures minimum gap between GAM API calls."""
    global _last_request_time
    with _api_lock:
        now = time.monotonic()
        wait = _MIN_REQUEST_INTERVAL - (now - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()

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
    """Convert GAM rate value to percentage. GAM returns rates as decimals
    (0.0–1.0), so multiply by 100.  If value is already > 1 assume it is
    already a percentage and use as-is.  Clamp to 0–100."""
    try:
        if value:
            d = Decimal(str(value))
            pct = d if d > 1 else d * 100
            return max(Decimal('0'), min(pct, Decimal('100')))
        return Decimal('0')
    except (ValueError, TypeError):
        return Decimal('0')


def _quantize(value: Decimal, places: int) -> Decimal:
    q = Decimal('1').scaleb(-places)
    try:
        return (value if isinstance(value, Decimal) else Decimal(str(value or '0'))).quantize(q, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0').quantize(q, rounding=ROUND_HALF_UP)


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
            GAMCredential = _get_gam_credential_model()

            credentials = (
                GAMCredential.objects
                .filter(is_connected=True, partner_admin__status='active')
                .select_related('partner_admin')
            )

            successful_count = 0
            failed_count = 0
            total_records_created = 0
            total_records_updated = 0

            for cred in credentials:
                partner = cred.partner_admin
                try:
                    result = GAMReportService._process_partner_network(
                        partner, cred, date_from, date_to
                    )
                    successful_count += 1
                    total_records_created += result.get('records_created', 0)
                    total_records_updated += result.get('records_updated', 0)
                except Exception as e:
                    failed_count += 1
                    label = cred.network_code or partner.email
                    logger.error(f"Failed to process partner {label}: {e}")
                    sync_log.add_network_error(label, str(e))

                    cred.connection_error = str(e)[:500]
                    cred.save(update_fields=['connection_error'])

            sync_log.mark_completed(successful_count, failed_count, total_records_created, total_records_updated)
            logger.info(f"Sync {sync_id} completed: {successful_count} success, {failed_count} failed")

            try:
                from .earnings_service import SubPublisherEarningsService
                spe_result = SubPublisherEarningsService.calculate_all(date_from, date_to)
                logger.info(f"Post-sync sub-publisher earnings: {spe_result}")
            except Exception as e:
                logger.error(f"Sub-publisher earnings calculation failed: {e}")

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
    # Per-partner network processing (new unified path)
    # ------------------------------------------------------------------
    @staticmethod
    def _process_partner_network(partner, cred, date_from, date_to):
        """Fetch all dimensions for a partner's entire GAM network."""
        try:
            client = GAMClientService.get_client_for_partner(partner)
        except Exception as e:
            if _is_auth_error(str(e)):
                return {'records_created': 0, 'records_updated': 0, 'status': 'skipped'}
            raise

        class _PartnerContext:
            def __init__(self):
                self.network_code = cred.network_code
                self.publisher_name = partner.company_name or partner.email
                self.publisher_id = partner.id

        result = GAMReportService._fetch_all_dimensions_parallel(
            client, _PartnerContext(), date_from, date_to
        )

        cred.last_synced_at = timezone.now()
        cred.connection_error = ''
        cred.save(update_fields=['last_synced_at', 'connection_error'])

        return result

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
                    logger.warning(f"Dimension {dk} ({td}) failed for {invitation.network_code}: {e}")

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
        Fetch a single dimension report.  If the full metric set fails,
        retry once without the ad-request metric so the report still lands.
        """
        dim_metrics = list(dimension_metrics.get(dimension_key, metrics))

        fallback = [m for m in dim_metrics if m != 'TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS']
        metric_variants = [dim_metrics]
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
                if 'EXCEEDED_QUOTA' in str(e):
                    wait = QUOTA_RETRY_DELAY + (QUOTA_RETRY_DELAY * 0.5)
                    logger.warning(f"Quota hit in fallback for {dimension_key}, sleeping {wait}s")
                    time.sleep(wait)
                logger.debug(f"Metric variant failed for {dimension_key}, trying fallback: {e}")

        raise last_error

    @staticmethod
    def _fetch_single_dimension(client, invitation, dimension_key, metrics_list, date_from, date_to):
        """
        Execute a single GAM report query, download gzipped CSV, parse rows.
        """
        dimensions = list(GAMReportService.DIMENSION_MAP.get(dimension_key, []))

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

        report_job = {"reportQuery": report_query}

        report_downloader = None
        report_job_id = None
        for _attempt in range(MAX_QUOTA_RETRIES):
            try:
                _throttle()
                if report_downloader is None:
                    report_downloader = client.GetDataDownloader(version="v202508")
                report_job_id = report_downloader.WaitForReport(report_job)
                break
            except Exception as e:
                if _is_auth_error(str(e)):
                    return {'skipped_due_to_auth_error': True, 'records': []}
                if 'EXCEEDED_QUOTA' in str(e) and _attempt < MAX_QUOTA_RETRIES - 1:
                    wait = QUOTA_RETRY_DELAY * (2 ** _attempt)
                    logger.warning(f"Quota hit (WaitForReport), retry {_attempt + 1} in {wait}s")
                    time.sleep(wait)
                    continue
                raise

        for _attempt in range(MAX_QUOTA_RETRIES):
            try:
                _throttle()
                with tempfile.TemporaryFile() as fp:
                    report_downloader.DownloadReportToFile(
                        report_job_id, 'GZIPPED_CSV', fp, include_totals_row=True
                    )
                    fp.seek(0)
                    decompressed = gzip.decompress(fp.read()).decode('utf-8', errors='ignore')
                break
            except Exception as e:
                if 'EXCEEDED_QUOTA' in str(e) and _attempt < MAX_QUOTA_RETRIES - 1:
                    wait = QUOTA_RETRY_DELAY * (2 ** _attempt)
                    logger.warning(f"Quota hit (Download), retry {_attempt + 1} in {wait}s")
                    time.sleep(wait)
                    continue
                raise

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
        network_code = invitation.network_code

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

                if dim_cols:
                    dimension_value = " | ".join(str(row.get(c, 'All')) for c in dim_cols)
                else:
                    dimension_value = 'All'

                if dimension_key == 'overview' and hasattr(invitation, 'publisher_name'):
                    dimension_value = invitation.publisher_name

                impressions = _safe_int(row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS', 0))
                revenue = _micros_to_currency(row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE', 0))
                clicks = _safe_int(row.get('AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS', 0))
                total_ad_requests = _safe_int(row.get('TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS', 0))

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
                    'publisher_id': getattr(invitation, 'publisher_id', None),
                    'network_code': network_code,
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

        unique_fields = ['network_code', 'date', 'dimension_type', 'dimension_value']
        update_fields = [
            'publisher_id', 'currency',
            'impressions', 'revenue', 'ecpm', 'clicks', 'ctr',
            'total_ad_requests', 'viewable_impressions_rate',
        ]

        for i in range(0, len(records_data), BATCH_SIZE):
            batch = records_data[i:i + BATCH_SIZE]
            objs = [
                MasterMetaData(
                    publisher_id=r.get('publisher_id'),
                    network_code=r['network_code'],
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

    @staticmethod
    def bulk_create_or_update_records(records_data):
        created, updated = GAMReportService._bulk_upsert_records(records_data)
        return {'created': created, 'updated': updated}
