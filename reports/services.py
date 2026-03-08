# reports/services.py - UPDATED with New Metrics

import logging
import tempfile
import gzip
import os
import csv
import io
import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from googleads import ad_manager
from googleads import errors as gam_errors

from .gam_client import GAMClientService
from accounts.models import User
from .models import MasterMetaData, ReportSyncLog
from .constants import dimension_map, metrics, dimension_metrics

logger = logging.getLogger(__name__)


class GAMReportService:
    """
    Optimized service for fetching GAM reports with enhanced error handling and performance
    """

    # Use dimension mapping and metrics from constants
    DIMENSION_MAP = dimension_map
    METRICS = metrics

    # Performance settings
    BATCH_SIZE = 1000  # Process records in batches
    MAX_RETRIES = 3    # Maximum retry attempts for failed API calls
    RETRY_DELAY = 5    # Seconds to wait between retries

    @staticmethod
    def bulk_create_or_update_records(records_data):
        """
        Efficiently bulk create or update MasterMetaData records
        """
        if not records_data:
            return {'created': 0, 'updated': 0}

        created_count = 0
        updated_count = 0

        # Process in batches for better memory management
        batch_size = GAMReportService.BATCH_SIZE
        for i in range(0, len(records_data), batch_size):
            batch = records_data[i:i + batch_size]

            with transaction.atomic():
                for record_data in batch:
                    try:
                        # Try to get existing record
                        existing_record = MasterMetaData.objects.filter(
                            parent_network=record_data['parent_network'],
                            child_network_code=record_data['child_network_code'],
                            dimension_type=record_data['dimension_type'],
                            dimension_value=record_data['dimension_value'],
                            date=record_data['date']
                        ).first()

                        if existing_record:
                            # Update existing record
                            for key, value in record_data.items():
                                setattr(existing_record, key, value)
                            existing_record.save()
                            updated_count += 1
                        else:
                            # Create new record
                            MasterMetaData.objects.create(**record_data)
                            created_count += 1

                    except Exception as e:
                        logger.error(f"Error processing record: {e}")
                        continue

        return {'created': created_count, 'updated': updated_count}

    @staticmethod
    def fetch_gam_reports(date_from=None, date_to=None, triggered_by=None):
        """
        Main cron job function - fetch reports for all eligible child networks
        UPDATED: New dimension mappings for managed inventory publisher dashboard
        """
        # Set default date range (last 4 days)
        if not date_from:
            date_to = timezone.now().date()
            date_from = date_to - timedelta(days=4)
        
        if not date_to:
            date_to = timezone.now().date()
        
        # Create sync log
        sync_id = f"sync_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        sync_log = ReportSyncLog.objects.create(
            sync_id=sync_id,
            date_from=date_from,
            date_to=date_to,
            triggered_by=triggered_by,
            is_manual=triggered_by is not None
        )
        
        logger.info(f"Starting GAM report sync {sync_id} for {date_from} to {date_to}")
        
        try:
            from core.models import StatusChoices
            
            # MCM publishers: require network_id
            mcm_publishers = User.objects.filter(
                role=User.UserRole.PUBLISHER,
                status=StatusChoices.ACTIVE,
                gam_type='mcm',
                network_id__isnull=False
            ).exclude(network_id='')
            
            # O&O publishers: require site_url (no network_id needed)
            oo_publishers = User.objects.filter(
                role=User.UserRole.PUBLISHER,
                status=StatusChoices.ACTIVE,
                gam_type='o_and_o',
                site_url__isnull=False
            ).exclude(site_url='')
            
            from itertools import chain
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
                    
                    logger.debug(f"Processed {publisher.network_id}: {result.get('records_created', 0)} created, {result.get('records_updated', 0)} updated")
                    
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e)
                    logger.error(f"❌ Failed to process publisher network {publisher.network_id}: {error_msg}")
                    sync_log.add_network_error(publisher.network_id or 'unknown', error_msg)
            
            # All processing completed successfully
            
            # Overview records are now created per account during _process_child_network
            
            # Mark sync as completed
            sync_log.mark_completed(successful_count, failed_count, total_records_created, total_records_updated)
            logger.info(f"Sync {sync_id} completed: {successful_count} success, {failed_count} failed")


            return {
                'success': True,
                'sync_id': sync_id,
                'successful_networks': successful_count,
                'failed_networks': failed_count,
                'total_records_created': total_records_created,
                'total_records_updated': total_records_updated
            }
            
        except Exception as e:
            logger.error(f"💥 Critical error in sync {sync_id}: {str(e)}")
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            return {
                'success': False,
                'sync_id': sync_id,
                'error': str(e)
            }

    @staticmethod
    def _process_publisher_network(publisher, date_from, date_to):
        """
        Process a single publisher network.
        MCM: uses parent YAML + CHILD_NETWORK_CODE filter.
        O&O: uses O&O YAML + SITE_NAME filter (no child network code).
        """
        publisher_gam_type = getattr(publisher, 'gam_type', 'mcm') or 'mcm'
        
        if publisher_gam_type == 'o_and_o':
            return GAMReportService._process_oo_publisher(publisher, date_from, date_to)
        
        return GAMReportService._process_mcm_publisher(publisher, date_from, date_to)

    @staticmethod
    def _process_mcm_publisher(publisher, date_from, date_to):
        """Process an MCM publisher using CHILD_NETWORK_CODE filter (original logic)."""
        child_network_code = publisher.network_id
        
        try:
            from django.conf import settings
            yaml_network_code = settings.GAM_PARENT_NETWORK_CODE
            
            yaml_filepath = os.path.join(settings.BASE_DIR, 'yaml_files', f"{yaml_network_code}.yaml")
            if not os.path.exists(yaml_filepath):
                raise FileNotFoundError(f"YAML file not found: {yaml_filepath}")
            
            try:
                client = GAMReportService._get_child_network_client(yaml_network_code)
            except Exception as client_error:
                error_message = str(client_error)
                logger.warning(f"❌ Failed to authenticate with GAM for {child_network_code}: {error_message}")
                if any(keyword in error_message for keyword in [
                    'AuthenticationError.NO_NETWORKS_TO_ACCESS',
                    'NO_NETWORKS_TO_ACCESS', 'AuthenticationError',
                    'authentication', 'unauthorized'
                ]):
                    return {
                        'records_created': 0, 'records_updated': 0,
                        'dimensions_processed': [], 'status': 'skipped',
                        'message': 'Authentication error - account skipped'
                    }
                raise
            
            dimension_results = {}
            
            class MockInvitation:
                def __init__(self, network_code, parent_code, publisher_obj):
                    self.child_network_code = network_code
                    self.delegation_type = 'MANAGE_INVENTORY'
                    self.gam_type = 'mcm'
                    self.parent_network = type('obj', (object,), {
                        'network_code': parent_code,
                        'network_name': 'Parent Network'
                    })()
                    self.publisher_name = f"{publisher_obj.company_name or publisher_obj.email}"
                    self.publisher_id = publisher_obj.id
            
            mock_invitation = MockInvitation(child_network_code, yaml_network_code, publisher)
            
            for dimension_key in dimension_map.keys():
                try:
                    records = GAMReportService._fetch_child_dimension_reports(
                        client=client, invitation=mock_invitation,
                        dimension_key=dimension_key,
                        date_from=date_from, date_to=date_to
                    )
                    dimension_results[dimension_key] = {'success': True, 'records': records}
                except Exception as dim_error:
                    logger.error(f"❌ Error processing {dimension_key}: {str(dim_error)}")
                    dimension_results[dimension_key] = {'success': False, 'error': str(dim_error)}
            
            total_records = sum(
                r['records'] for r in dimension_results.values()
                if r.get('success') and isinstance(r.get('records'), int)
            )
            
            return {
                'records_created': total_records, 'records_updated': 0,
                'dimensions_processed': list(dimension_results.keys()),
                'dimension_results': dimension_results
            }
        except Exception as e:
            logger.error(f"❌ Error processing MCM publisher {child_network_code}: {str(e)}")
            raise

    @staticmethod
    def _process_oo_publisher(publisher, date_from, date_to):
        """
        Process an O&O publisher using SITE_NAME filter instead of CHILD_NETWORK_CODE.
        Reports are fetched from the O&O GAM network, filtered by the publisher's site URL.
        """
        from urllib.parse import urlparse
        from decouple import config as decouple_config
        
        site_url = publisher.site_url
        if not site_url:
            logger.warning(f"⚠️ O&O publisher {publisher.email} has no site_url - skipping")
            return {'records_created': 0, 'records_updated': 0, 'dimensions_processed': [], 'status': 'skipped'}
        
        # Normalize site URL to domain (GAM stores as "example.com")
        parsed = urlparse(site_url) if '://' in site_url else urlparse(f'https://{site_url}')
        domain = parsed.netloc or parsed.path.split('/')[0]
        if domain.startswith('www.'):
            domain = domain[4:]
        domain = domain.rstrip('/').split(':')[0]
        
        oo_network_code = decouple_config('GAM_OO_NETWORK_CODE', default='23341212234')
        
        try:
            client = GAMClientService.get_googleads_client(oo_network_code, gam_type='o_and_o')
        except Exception as client_error:
            error_message = str(client_error)
            logger.warning(f"❌ Failed to authenticate with O&O GAM for {publisher.email}: {error_message}")
            if any(kw in error_message for kw in [
                'AuthenticationError', 'NO_NETWORKS_TO_ACCESS',
                'authentication', 'unauthorized'
            ]):
                return {
                    'records_created': 0, 'records_updated': 0,
                    'dimensions_processed': [], 'status': 'skipped',
                    'message': 'O&O authentication error - account skipped'
                }
            raise
        
        dimension_results = {}
        
        class OOInvitation:
            """Mock invitation for O&O publishers - uses SITE_NAME filter instead of CHILD_NETWORK_CODE."""
            def __init__(self, site_domain, oo_network, publisher_obj):
                self.child_network_code = site_domain
                self.delegation_type = 'OWNED_AND_OPERATED'
                self.gam_type = 'o_and_o'
                self.site_domain = site_domain
                self.parent_network = type('obj', (object,), {
                    'network_code': oo_network,
                    'network_name': 'O&O Network'
                })()
                self.publisher_name = f"{publisher_obj.company_name or publisher_obj.email}"
                self.publisher_id = publisher_obj.id
        
        oo_invitation = OOInvitation(domain, oo_network_code, publisher)
        
        for dimension_key in dimension_map.keys():
            try:
                records = GAMReportService._fetch_child_dimension_reports(
                    client=client, invitation=oo_invitation,
                    dimension_key=dimension_key,
                    date_from=date_from, date_to=date_to
                )
                dimension_results[dimension_key] = {'success': True, 'records': records}
            except Exception as dim_error:
                logger.error(f"❌ O&O error processing {dimension_key} for {domain}: {str(dim_error)}")
                dimension_results[dimension_key] = {'success': False, 'error': str(dim_error)}
        
        total_records = sum(
            r['records'] for r in dimension_results.values()
            if r.get('success') and isinstance(r.get('records'), int)
        )
        
        return {
            'records_created': total_records, 'records_updated': 0,
            'dimensions_processed': list(dimension_results.keys()),
            'dimension_results': dimension_results
        }

    @staticmethod
    def _process_child_network(invitation, date_from, date_to):
        """
        Process a single child network using its own YAML file
        UPDATED: Handles new metrics and USD currency with early exit on auth errors
        """
        child_network_code = invitation.child_network_code
        delegation_type = invitation.delegation_type
        
        try:
            # Determine which YAML file to use based on delegation type
            # For managed inventory, always use parent network YAML
            from decouple import config
            parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='23310681755')
            
            if delegation_type == 'MANAGE_ACCOUNT':
                yaml_network_code = child_network_code
                target_network_code = child_network_code
            else:
                # Use parent network for MANAGE_INVENTORY
                yaml_network_code = parent_network_code
                target_network_code = parent_network_code
            
            # Check if YAML file exists
            yaml_filepath = os.path.join(settings.BASE_DIR, 'yaml_files', f"{yaml_network_code}.yaml")
            if not os.path.exists(yaml_filepath):
                logger.warning(f"⚠️ YAML file not found: {yaml_filepath}")
                raise FileNotFoundError(f"YAML file not found: {yaml_filepath}")
            
            
            try:
                # Get GAM client directly for child network (no parent dependency)
                client = GAMReportService._get_child_network_client(child_network_code)
                
                
            except Exception as client_error:
                error_message = str(client_error)
                logger.warning(f"❌ Failed to authenticate with GAM for {child_network_code}: {error_message}")
                
                # Check if it's an authentication error that should skip the account
                if any(keyword in error_message for keyword in [
                    'AuthenticationError.NO_NETWORKS_TO_ACCESS',
                    'NO_NETWORKS_TO_ACCESS',
                    'AuthenticationError',
                    'authentication',
                    'unauthorized',
                    'forbidden',
                    'invalid credentials',
                    'access denied'
                ]):
                    logger.warning(f"🚫 Authentication error detected for {child_network_code} - skipping account and disabling service key")
                    # Return early with no records - skip all dimensions
                    return {
                        'records_created': 0,
                        'records_updated': 0,
                        'skipped_due_to_auth_error': True
                    }
                else:
                    raise
            
            records_created = 0
            records_updated = 0
            
            # Process device category first
            device_category_processed = False
            
            # Process each dimension type (including overview with DATE dimension)
            for dimension_key in GAMReportService.DIMENSION_MAP.keys():
                
                try:
                    result = GAMReportService._fetch_child_dimension_reports(
                        client, invitation, dimension_key, date_from, date_to
                    )
                    
                    # Check if account was skipped due to authentication error
                    if result.get('skipped_due_to_auth_error', False):
                        logger.warning(f"🚫 Account {child_network_code} skipped due to authentication error - stopping all dimension processing")
                        # Return early with current records - skip all remaining dimensions
                        return {
                            'records_created': records_created,
                            'records_updated': records_updated,
                            'skipped_due_to_auth_error': True
                        }
                    
                    records_created += result['records_created']
                    records_updated += result['records_updated']
                    
                    # Mark device category as processed
                    if dimension_key == 'deviceCategory':
                        device_category_processed = True
                    
                except Exception as e:
                    error_message = str(e)
                    logger.warning(f"⚠️ Failed to fetch {dimension_key} for {child_network_code}: {error_message}")
                    
                    # Check if it's an authentication error that should skip the account
                    auth_error_keywords = [
                        'AuthenticationError.NO_NETWORKS_TO_ACCESS',
                        'NO_NETWORKS_TO_ACCESS',
                        'AuthenticationError',
                        'authentication',
                        'unauthorized',
                        'forbidden',
                        'invalid credentials',
                        'access denied'
                    ]
                    
                    is_auth_error = any(keyword in error_message for keyword in auth_error_keywords)
                    
                    if is_auth_error:
                        logger.warning(f"🚫 Authentication error detected in main loop for {child_network_code} - skipping account and disabling service key")
                        # Return early with current records - skip all remaining dimensions
                        return {
                            'records_created': records_created,
                            'records_updated': records_updated,
                            'skipped_due_to_auth_error': True
                        }
                    else:
                        # For other errors, continue to next dimension
                        continue
            
            # All metrics processing completed for this child network
            
            return {
                'records_created': records_created,
                'records_updated': records_updated
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to process child network {child_network_code}: {str(e)}")
            raise

    @staticmethod
    def _get_child_network_client(child_network_code, gam_type='mcm'):
        """Get GAM client using the appropriate YAML configuration"""
        try:
            return GAMClientService.get_googleads_client(child_network_code, gam_type=gam_type)
        except Exception as e:
            logger.warning(f"⚠️ Failed to get client for {child_network_code} (gam_type={gam_type}): {str(e)}")
            raise
    

    @staticmethod
    def _fetch_child_dimension_reports(client, invitation, dimension_key, date_from, date_to):
        """
        Fetch reports using real GAM API.
        MCM (MANAGE_INVENTORY): filters by CHILD_NETWORK_CODE.
        O&O (OWNED_AND_OPERATED): filters by SITE_NAME (domain).
        """

        try:
            dimensions = list(GAMReportService.DIMENSION_MAP.get(dimension_key, []))
            filter_statement = None
            
            is_oo = getattr(invitation, 'gam_type', None) == 'o_and_o' or invitation.delegation_type == 'OWNED_AND_OPERATED'
            
            if is_oo:
                # O&O: ensure SITE_NAME is in dimensions and filter by it
                if "SITE_NAME" not in dimensions:
                    dimensions.append("SITE_NAME")
                site_domain = getattr(invitation, 'site_domain', invitation.child_network_code)
                filter_statement = {
                    'query': 'WHERE SITE_NAME = :siteName',
                    'values': [
                        {
                            'key': 'siteName',
                            'value': {'xsi_type': 'TextValue', 'value': str(site_domain)}
                        }
                    ]
                }
            elif invitation.delegation_type == 'MANAGE_INVENTORY':
                if "CHILD_NETWORK_CODE" not in dimensions:
                    dimensions.append("CHILD_NETWORK_CODE")
                filter_statement = {
                    'query': 'WHERE CHILD_NETWORK_CODE = :childNetworkCode',
                    'values': [
                        {
                            'key': 'childNetworkCode',
                            'value': {'xsi_type': 'TextValue', 'value': str(invitation.child_network_code)}
                        }
                    ]
                }
            
            # Get dimension-specific metrics
            dimension_specific_metrics = dimension_metrics.get(dimension_key, GAMReportService.METRICS)
            
            # Report job with dimension-specific metrics
            report_query = {
                "dimensions": dimensions,
                "columns": dimension_specific_metrics,
                "dateRangeType": "CUSTOM_DATE",
                "startDate": date_from,
                "endDate": date_to,
                "reportCurrency": "USD",  # Force USD currency for all reports
            }
            # Only include adUnitView when an AD_UNIT dimension is requested
            if "AD_UNIT_NAME" in dimensions:
                report_query["adUnitView"] = "FLAT"
            if filter_statement:
                report_query["statement"] = filter_statement

            report_job = {"reportQuery": report_query}
            
            
            # Download report with authentication error handling
            try:
                report_downloader = client.GetDataDownloader(version="v202508")
                report_job_id = report_downloader.WaitForReport(report_job)
            except Exception as report_error:
                error_message = str(report_error)
                logger.warning(f"❌ Report execution failed for {dimension_key} in {invitation.child_network_code}: {error_message}")
                
                # Check if it's an authentication error that should skip the account
                auth_error_keywords = [
                    'AuthenticationError.NO_NETWORKS_TO_ACCESS',
                    'NO_NETWORKS_TO_ACCESS',
                    'AuthenticationError',
                    'authentication',
                    'unauthorized',
                    'forbidden',
                    'invalid credentials',
                    'access denied'
                ]
                
                is_auth_error = any(keyword in error_message for keyword in auth_error_keywords)
                
                if is_auth_error:
                    logger.warning(f"🚫 Authentication error detected during report fetch for {invitation.child_network_code} - skipping account and disabling service key")
                    # Return early with no records - skip this dimension and all future dimensions
                    return {
                        'records_created': 0,
                        'records_updated': 0,
                        'skipped_due_to_auth_error': True
                    }
                else:
                    # For other errors, re-raise to be handled by the calling method
                    raise
            
            records_created = 0
            records_updated = 0
            
            with tempfile.TemporaryFile() as fp:
                # Use gzipped CSV to align with gzip.decompress below
                report_downloader.DownloadReportToFile(report_job_id, 'GZIPPED_CSV', fp, include_totals_row=True)
                fp.seek(0)

                # Decompress and process data using CSV reader
                decompressed_text = gzip.decompress(fp.read()).decode('utf-8', errors='ignore')
                reader = csv.reader(io.StringIO(decompressed_text))
                rows = list(reader)

                if len(rows) <= 1:
                    return {'records_created': 0, 'records_updated': 0}

                headers = [col.replace('Dimension.', '').replace('Column.', '') for col in rows[0]]

                logger.debug(f"Processing {len(rows)-1} rows for {dimension_key} report")

                processed_records = GAMReportService._process_report_data(
                    headers, rows[1:], invitation, dimension_key, date_from, date_to
                )

                # Process dimension data

                for record_data in processed_records:
                    if record_data:
                        result = GAMReportService._store_report_data(record_data)
                        if result:
                            records_created += result.get('created', 0)
                            records_updated += result.get('updated', 0)

            return {'records_created': records_created, 'records_updated': records_updated}

        except Exception as e:
            logger.error(f"❌ Error fetching {dimension_key} for {invitation.child_network_code}: {e}")
            raise

    @staticmethod
    def _get_real_dimension_values(client, dimension_key, gam_dimensions):
        """
        Get real dimension values from GAM API or use realistic defaults
        """
        try:
            # TODO: Implement real GAM API call to get dimension values
            # For now, use realistic defaults based on dimension type
            return GAMReportService._get_dimension_values(dimension_key)
        except Exception as e:
            logger.warning(f"Failed to get real dimension values for {dimension_key}: {e}")
            return GAMReportService._get_dimension_values(dimension_key)

    @staticmethod
    def _get_dimension_values(dimension_key):
        """
        Get realistic dimension values for testing - Updated for Managed Inventory Publisher Dashboard
        """
        dimension_values_map = {
            'overview': ['Total'],
            'site': ['example.com', 'testsite.net', 'demo.org', 'sample.io'],
            'trafficSource': ['Direct', 'Google Search', 'Facebook', 'Twitter', 'Email'],
            'deviceCategory': ['Desktop', 'Mobile', 'Tablet'],
            'country': ['United States', 'Canada', 'United Kingdom', 'Germany', 'France'],
            'adunit': ['Leaderboard', 'Banner', 'Skyscraper', 'Rectangle', 'Mobile Banner'],
            'inventoryFormat': ['Display', 'Video', 'Mobile', 'Native', 'Rich Media'],
            'browser': ['Chrome', 'Safari', 'Firefox', 'Edge', 'Opera']
        }

        return dimension_values_map.get(dimension_key, ['All'])

    @staticmethod
    def _process_report_data(headers, report_data, invitation, dimension_key, date_from, date_to):
        """
        REPLICATED: Process report data for each dimension value separately
        """
        processed_records = []
        
        # Process each row as a separate record
        for row_data in report_data:
            try:
                row_dict = dict(zip(headers, row_data))

                # Skip GAM totals row if present in CSV (dimension value equals 'Total')
                try:
                    for dim_col in (
                        'SITE_NAME', 'AD_UNIT_NAME', 'MOBILE_APP_NAME',
                        'DEVICE_CATEGORY_NAME', 'COUNTRY_NAME',
                        'MOBILE_CARRIER_NAME', 'CARRIER_NAME', 'BROWSER_NAME',
                        'INVENTORY_FORMAT', 'INVENTORY_FORMAT_NAME'
                    ):
                        if dim_col in row_dict:
                            val = str(row_dict.get(dim_col) or '').strip().lower()
                            if val in ('total', 'totals', ''):
                                raise StopIteration
                except StopIteration:
                    # Skip this totals row
                    continue
                
                # Get dimension value
                dimension_value = None
                dim_cols = GAMReportService.DIMENSION_MAP.get(dimension_key, [])
                if dim_cols:
                    parts = []
                    for col in dim_cols:
                        parts.append(str(row_dict.get(col, 'All')))
                    dimension_value = " | ".join(parts)
                
                # For overview dimension, use publisher name instead of date
                if dimension_key == 'overview' and hasattr(invitation, 'publisher_name'):
                    dimension_value = invitation.publisher_name
                
                # Convert and process data - use all available API data directly
                impressions = GAMReportService._safe_int(row_dict.get('AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS', 0))
                # Convert micros currency (GAM returns monetary values in micros)
                revenue = GAMReportService._convert_micros_to_currency(row_dict.get('AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE', 0))
                clicks = GAMReportService._safe_int(row_dict.get('AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS', 0))
                total_ad_requests = GAMReportService._safe_int(row_dict.get('TOTAL_AD_REQUESTS', 0))
                total_ad_requests += GAMReportService._safe_int(row_dict.get('TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS', 0))
                
                # Use API-provided metrics directly instead of manual calculations
                api_ecpm = row_dict.get('AD_EXCHANGE_LINE_ITEM_LEVEL_AVERAGE_ECPM', 0)
                api_ctr = row_dict.get('AD_EXCHANGE_LINE_ITEM_LEVEL_CTR', 0)
                
                # Convert API-provided ECPM and CTR (API returns as decimal, convert to percentage for CTR)
                ecpm = GAMReportService._convert_micros_to_currency(api_ecpm) if api_ecpm else Decimal('0')
                ctr = GAMReportService._convert_decimal_to_percentage(api_ctr) if api_ctr else Decimal('0')
                
                # Fallback to manual calculation if API values are not available
                if ecpm == 0 and impressions > 0:
                    ecpm = (revenue / impressions) * 1000
                if ctr == 0 and impressions > 0:
                    ctr = (clicks / impressions) * 100
                
                fill_rate = Decimal('0')
                if total_ad_requests > 0:
                    fill_rate = (impressions / total_ad_requests) * 100
                
                # Get viewability rate
                viewable_impressions_rate = GAMReportService._convert_decimal_to_percentage(
                    row_dict.get('AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE')
                )
                # Enforce model precision constraints
                revenue = GAMReportService._quantize(revenue, 2)
                ecpm = GAMReportService._quantize(ecpm, 2)  # Model constraint: decimal_places=2
                ctr = GAMReportService._quantize(ctr, 2)
                fill_rate = GAMReportService._quantize(fill_rate, 2)
                viewable_impressions_rate = GAMReportService._quantize(viewable_impressions_rate, 2)
                
                from decouple import config
                is_oo = getattr(invitation, 'gam_type', None) == 'o_and_o' or invitation.delegation_type == 'OWNED_AND_OPERATED'
                if is_oo:
                    parent_network_code = config('GAM_OO_NETWORK_CODE', default='23341212234')
                else:
                    parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='23310681755')
                
                # Create record data
                record_data = {
                    'parent_network_code': parent_network_code,
                    'publisher_id': getattr(invitation, 'publisher_id', None),  # Use publisher_id from invitation
                    'child_network_code': invitation.child_network_code,
                    'dimension_type': dimension_key,
                    'dimension_value': dimension_value,
                    'date': date_from,  # Use date_from for main reports (single date)
                    'currency': 'USD',
                    'impressions': impressions,
                    'revenue': revenue,
                    'ecpm': ecpm,
                    'clicks': clicks,
                    'ctr': ctr,
                    'total_ad_requests': total_ad_requests,
                    'viewable_impressions_rate': viewable_impressions_rate,
                }
                
                processed_records.append(record_data)
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to process row: {str(e)}")
                continue
        
        return processed_records

    @staticmethod
    def _store_report_data(data):
        """
        Store report data in database with duplicate prevention
        Updated for publisher-based model without invitation/parent_network fields
        """
        try:
            # For overview records, use child_network_code + date as unique constraint
            if data['dimension_type'] == 'overview':
                record, created = MasterMetaData.objects.update_or_create(
                    parent_network_code=data['parent_network_code'],
                    child_network_code=data['child_network_code'],
                    dimension_type=data['dimension_type'],
                    date=data['date'],
                    defaults={
                        'publisher_id': data.get('publisher_id'),
                        'dimension_value': data['dimension_value'],
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
                )
            else:
                # For other dimensions, use standard fields
                record, created = MasterMetaData.objects.update_or_create(
                    parent_network_code=data['parent_network_code'],
                    child_network_code=data['child_network_code'],
                    dimension_type=data['dimension_type'],
                    dimension_value=data['dimension_value'],
                    date=data['date'],
                    defaults={
                        'publisher_id': data.get('publisher_id'),
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
                )
            
            logger.debug(f"Stored report data: {data['child_network_code']} - {data['dimension_type']}")
            return {'created': 1 if created else 0, 'updated': 0 if created else 1}
            
        except Exception as e:
            logger.error(f"❌ Failed to store report data: {str(e)}")
            return None

    # REPLICATED: Helper methods from sub-reports
    @staticmethod
    def _safe_int(value):
        """Safely convert value to integer"""
        try:
            return int(float(value)) if value else 0
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _convert_micros_to_currency(value):
        """Convert GAM micros to currency units"""
        try:
            if value is None or value == "":
                return Decimal('0')
            return Decimal(str(value)) / Decimal('1000000')
        except (ValueError, TypeError):
            return Decimal('0')

    @staticmethod
    def _convert_decimal_to_percentage(value):
        """Convert decimal to percentage"""
        try:
            if value:
                return Decimal(str(value)) * 100
            return Decimal('0')
        except (ValueError, TypeError):
            return Decimal('0')

    @staticmethod
    def _quantize(value: Decimal, places: int) -> Decimal:
        """Quantize Decimal to a fixed number of places using HALF_UP rounding."""
        try:
            from decimal import ROUND_HALF_UP
            q = Decimal('1').scaleb(-places)
            return (value if isinstance(value, Decimal) else Decimal(str(value or '0'))).quantize(q, rounding=ROUND_HALF_UP)
        except Exception:
            from decimal import ROUND_HALF_UP
            return Decimal('0').quantize(Decimal('1').scaleb(-places), rounding=ROUND_HALF_UP)



    # Sub-reports functionality removed - no longer needed for managed inventory publisher dashboard





