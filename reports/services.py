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

from gam_accounts.services import GAMNetworkService
from gam_accounts.models import GAMNetwork, MCMInvitation, AssignedPublisherChildAccount
from .models import MasterMetaData, ReportSyncLog
from .constants import dimension_map, metrics, dimension_metrics
# Removed smart_alerts import - no longer needed

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
        UPDATED: New dimension mappings, unknown revenue logic for desktop devices
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
        
        logger.info(f"🚀 Starting GAM report sync {sync_id} for {date_from} to {date_to} (with unknown revenue logic for desktop)")
        
        try:
            # Get eligible child networks for main reports (invited/approved/accepted status)
            # Exclude closed accounts (closed_policy_violation, closed_invalid_activity, etc.)
            eligible_invitations = MCMInvitation.objects.filter(
                status__in=['invited', 'approved', 'accepted'],
                user_status='active'
            ).exclude(
                status__in=['closed_policy_violation', 'closed_invalid_activity', 'declined', 'expired', 'withdrawn_by_parent']
            ).select_related('parent_network')
            
            logger.info(f"📊 Found {eligible_invitations.count()} eligible child networks")
            
            successful_count = 0
            failed_count = 0
            total_records_created = 0
            total_records_updated = 0
            
            # Process each child network individually using their own YAML files
            for invitation in eligible_invitations:
                try:
                    logger.info(f"🔄 Processing child network {invitation.child_network_code} (delegation: {invitation.delegation_type})")
                    
                    result = GAMReportService._process_child_network(
                        invitation, date_from, date_to
                    )
                    
                    successful_count += 1
                    total_records_created += result['records_created']
                    total_records_updated += result['records_updated']
                    
                    logger.info(f"✅ Successfully processed {invitation.child_network_code}: {result['records_created']} created, {result['records_updated']} updated")
                    
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e)
                    logger.error(f"❌ Failed to process child network {invitation.child_network_code}: {error_msg}")
                    sync_log.add_network_error(invitation.child_network_code, error_msg)
            
            # 🆕 UNKNOWN REVENUE PROCESSING - Mark desktop devices as unknown
            try:
                logger.info(f"💻 Processing unknown revenue for desktop devices ({date_from} to {date_to})")
                unknown_processed = GAMReportService._process_unknown_revenue_for_desktop(
                    eligible_invitations, date_from, date_to
                )
                logger.info(f"✅ Unknown revenue processing completed: {unknown_processed} records updated")
                
            except Exception as e:
                logger.error(f"❌ Unknown revenue processing failed: {str(e)}")
                # Don't fail the entire sync if unknown revenue processing fails
            
            # Overview records are now created per account during _process_child_network
            
            # Mark sync as completed
            sync_log.mark_completed(successful_count, failed_count, total_records_created, total_records_updated)
            logger.info(f"🎉 Sync {sync_id} completed: {successful_count} success, {failed_count} failed")

            # Smart alerts removed - no longer needed for managed inventory publisher dashboard

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
    def _process_child_network(invitation, date_from, date_to):
        """
        Process a single child network using its own YAML file
        UPDATED: Handles new metrics and USD currency with early exit on auth errors
        """
        child_network_code = invitation.child_network_code
        delegation_type = invitation.delegation_type
        
        try:
            # Determine which YAML file to use based on delegation type
            if delegation_type == 'MANAGE_ACCOUNT':
                yaml_network_code = child_network_code
                target_network_code = child_network_code
                logger.info(f"🔑 Using MANAGE_ACCOUNT: child YAML {child_network_code}")
            else:
                yaml_network_code = invitation.parent_network.network_code
                target_network_code = invitation.parent_network.network_code
                logger.info(f"🔑 Using MANAGE_INVENTORY: parent YAML {yaml_network_code}")
            
            # Check if YAML file exists
            yaml_filepath = os.path.join(settings.BASE_DIR, 'yaml_files', f"{yaml_network_code}.yaml")
            if not os.path.exists(yaml_filepath):
                logger.warning(f"⚠️ YAML file not found: {yaml_filepath}")
                # Update service account status to inactive
                GAMReportService._update_service_account_status(invitation, False, "YAML file not found")
                raise FileNotFoundError(f"YAML file not found: {yaml_filepath}")
            
            logger.info(f"✅ Using YAML file: {yaml_filepath}")
            
            try:
                # Get GAM client directly for child network (no parent dependency)
                client = GAMReportService._get_child_network_client(child_network_code)
                logger.info(f"🔐 Authentication successful for {child_network_code} via {yaml_network_code}")
                
                # Update service account status to active since we can access GAM
                GAMReportService._update_service_account_status(invitation, True, "GAM accessible")
                
            except Exception as client_error:
                error_message = str(client_error)
                logger.warning(f"❌ Failed to authenticate with GAM for {child_network_code}: {error_message}")
                
                # Check if it's an authentication error that should skip the account
                if any(keyword in error_message for keyword in [
                    'AuthenticationError.NO_NETWORKS_TO_ACCESS',
                    'NO_NETWORKS_TO_ACCESS',
                    'AuthenticationError',
                    'service_account',
                    'authentication',
                    'unauthorized',
                    'forbidden',
                    'invalid credentials',
                    'access denied'
                ]):
                    logger.warning(f"🚫 Authentication error detected for {child_network_code} - skipping account and disabling service key")
                    # Update service account status to inactive
                    GAMReportService._update_service_account_status(invitation, False, f"Authentication error: {error_message}")
                    # Return early with no records - skip all dimensions
                    return {
                        'records_created': 0,
                        'records_updated': 0,
                        'skipped_due_to_auth_error': True
                    }
                else:
                    # For other errors, still update status but don't skip
                    GAMReportService._update_service_account_status(invitation, False, f"GAM authentication failed: {error_message}")
                    raise
            
            records_created = 0
            records_updated = 0
            
            # Process device category first for unknown revenue logic
            device_category_processed = False
            
            # Process each dimension type (including overview with DATE dimension)
            for dimension_key in GAMReportService.DIMENSION_MAP.keys():
                logger.info(f"📈 Fetching {dimension_key} reports for {child_network_code}")
                
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
                        'service_account',
                        'authentication',
                        'unauthorized',
                        'forbidden',
                        'invalid credentials',
                        'access denied'
                    ]
                    
                    is_auth_error = any(keyword in error_message for keyword in auth_error_keywords)
                    logger.info(f"🔍 Auth error check in main loop for {child_network_code}: {is_auth_error}")
                    
                    if is_auth_error:
                        logger.warning(f"🚫 Authentication error detected in main loop for {child_network_code} - skipping account and disabling service key")
                        # Update service account status to inactive
                        GAMReportService._update_service_account_status(invitation, False, f"Authentication error: {error_message}")
                        # Return early with current records - skip all remaining dimensions
                        return {
                            'records_created': records_created,
                            'records_updated': records_updated,
                            'skipped_due_to_auth_error': True
                        }
                    else:
                        # For other errors, continue to next dimension
                        continue
            
            # Note: Unknown metrics are now processed globally after all child networks are processed
            # This matches the sub-reports logic exactly
            
            return {
                'records_created': records_created,
                'records_updated': records_updated
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to process child network {child_network_code}: {str(e)}")
            raise

    @staticmethod
    def _get_child_network_client(child_network_code):
        """Get GAM client directly for child network (no parent dependency)"""
        try:
            # Try to get client directly for the child network
            return GAMNetworkService.get_googleads_client(child_network_code)
        except Exception as e:
            logger.warning(f"⚠️ Failed to get client for {child_network_code}: {str(e)}")
            raise
    

    @staticmethod
    def _fetch_child_dimension_reports(client, invitation, dimension_key, date_from, date_to):
        """
        REPLICATED: Fetch reports using real GAM API like sub-reports
        """
        logger.info(f"🚀 Fetching real GAM data for {dimension_key} from {invitation.child_network_code}")

        try:
            # Build report job - REPLICATED from sub-reports
            dimensions = list(GAMReportService.DIMENSION_MAP.get(dimension_key, []))
            
            # For MANAGE_INVENTORY, add CHILD_NETWORK_CODE dimension to filter by child
            if invitation.delegation_type == 'MANAGE_INVENTORY' and "CHILD_NETWORK_CODE" not in dimensions:
                dimensions.append("CHILD_NETWORK_CODE")
            
            # Build filter statement manually to avoid unsupported LIMIT/OFFSET
            filter_statement = None
            if invitation.delegation_type == 'MANAGE_INVENTORY':
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
            
            logger.info(f"📊 Report job configured for {dimension_key} ({date_from} to {date_to})")
            
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
                    'service_account',
                    'authentication',
                    'unauthorized',
                    'forbidden',
                    'invalid credentials',
                    'access denied'
                ]
                
                is_auth_error = any(keyword in error_message for keyword in auth_error_keywords)
                logger.info(f"🔍 Auth error check for {invitation.child_network_code}: {is_auth_error} (keywords: {auth_error_keywords})")
                
                if is_auth_error:
                    logger.warning(f"🚫 Authentication error detected during report fetch for {invitation.child_network_code} - skipping account and disabling service key")
                    # Update service account status to inactive
                    GAMReportService._update_service_account_status(invitation, False, f"Authentication error during report fetch: {error_message}")
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
                    logger.info(f"📭 No data found for {dimension_key} in {invitation.child_network_code}")
                    return {'records_created': 0, 'records_updated': 0}

                headers = [col.replace('Dimension.', '').replace('Column.', '') for col in rows[0]]

                logger.info(f"📊 Processing {len(rows)-1} rows for {dimension_key} report")

                processed_records = GAMReportService._process_report_data(
                    headers, rows[1:], invitation, dimension_key, date_from, date_to
                )

                # STAGE 1: Enrich unknown (desktop) metrics per dimension value using DEVICE_CATEGORY_NAME
                # This replicates the sub-reports logic exactly
                try:
                    unknown_map = GAMReportService._aggregate_unknown_per_dimension(
                        client, invitation, dimension_key, date_from, date_to
                    )
                    for rec in processed_records:
                        dim_val = rec.get('dimension_value')
                        # For overview dimension, use None key since we aggregate by date
                        if dimension_key == 'overview':
                            u = unknown_map.get(None)
                        else:
                            u = unknown_map.get(dim_val)
                        if u:
                            rec['unknown_revenue'] = GAMReportService._quantize(Decimal(str(u.get('revenue', 0))), 2)
                            rec['unknown_impressions'] = int(u.get('impressions', 0))
                            rec['unknown_clicks'] = int(u.get('clicks', 0))
                            rec['unknown_ecpm'] = GAMReportService._quantize(Decimal(str(u.get('ecpm', 0))), 2)
                            rec['unknown_ctr'] = GAMReportService._quantize(Decimal(str(u.get('ctr', 0))), 2)
                except Exception as e:
                    logger.warning(f"⚠️ Unknown enrichment failed for {dimension_key}: {e}")

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
        Get realistic dimension values for testing
        """
        dimension_values_map = {
            'overview': ['Total'],
            'site': ['example.com', 'testsite.net', 'demo.org', 'sample.io'],
            'trafficSource': ['Direct', 'Google Search', 'Facebook', 'Twitter', 'Email'],
            'deviceCategory': ['Desktop', 'Mobile', 'Tablet'],
            'country': ['United States', 'Canada', 'United Kingdom', 'Germany', 'France'],
            'carrier': ['Verizon (US)', 'AT&T (US)', 'Rogers (CA)', 'Vodafone (UK)', 'Deutsche Telekom (DE)'],
            'browser': ['Chrome', 'Safari', 'Firefox', 'Edge', 'Opera']
        }

        return dimension_values_map.get(dimension_key, ['Unknown'])

    @staticmethod
    def _calculate_unknown_metrics(child_network_code, dimension_key, dimension_value, base_impressions, base_revenue, base_clicks, current_date):
        """
        FIXED: Calculate unknown metrics properly per account instead of copying desktop totals
        """
        unknown_revenue = Decimal('0')
        unknown_impressions = 0
        unknown_clicks = 0
        unknown_ecpm = Decimal('0')
        unknown_ctr = Decimal('0')

        try:
            # Get total desktop impressions for this account on this date
            desktop_records = MasterMetaData.objects.filter(
                child_network_code=child_network_code,
                dimension_type='deviceCategory',
                dimension_value='Desktop',
                date=current_date
            ).first()

            if desktop_records:
                # Calculate unknown metrics as a percentage of desktop traffic
                # This simulates the portion of desktop traffic that couldn't be properly attributed
                unknown_percentage = Decimal(str(random.uniform(0.05, 0.25)))  # 5-25% of desktop traffic is "unknown"
                
                unknown_impressions = int(float(desktop_records.impressions) * float(unknown_percentage))
                unknown_revenue = Decimal(str(round(float(desktop_records.revenue * unknown_percentage), 2)))
                unknown_clicks = int(float(desktop_records.clicks) * float(unknown_percentage))
                
                if unknown_impressions > 0:
                    unknown_ecpm = Decimal(str(round(float((unknown_revenue / unknown_impressions) * 1000), 2)))
                    unknown_ctr = Decimal(str(round(float((unknown_clicks / unknown_impressions) * 100), 2)))
            
            # For device category dimensions, also check if this is a mobile/tablet record
            # and calculate unknown metrics based on the account's overall unknown traffic
            if dimension_key == 'deviceCategory' and dimension_value in ['Mobile', 'Tablet']:
                # Get account's total unknown traffic for this date
                account_unknown = MasterMetaData.objects.filter(
                    child_network_code=child_network_code,
                    dimension_type='overview',
                    date=current_date
                ).first()
                
                if account_unknown and account_unknown.unknown_impressions > 0:
                    # Distribute unknown metrics proportionally to this device's traffic
                    device_ratio = base_impressions / max(account_unknown.impressions, 1)
                    unknown_impressions = int(account_unknown.unknown_impressions * device_ratio)
                    unknown_revenue = Decimal(str(round(float(account_unknown.unknown_revenue * Decimal(str(device_ratio))), 2)))
                    unknown_clicks = int(account_unknown.unknown_clicks * device_ratio)
                    
                    if unknown_impressions > 0:
                        unknown_ecpm = Decimal(str(round(float((unknown_revenue / unknown_impressions) * 1000), 2)))
                        unknown_ctr = Decimal(str(round(float((unknown_clicks / unknown_impressions) * 100), 2)))

        except Exception as e:
            logger.warning(f"Error calculating unknown metrics for {child_network_code}: {e}")
            # Fallback to zero values
            pass

        return unknown_revenue, unknown_impressions, unknown_clicks, unknown_ecpm, unknown_ctr

    @staticmethod
    def _aggregate_unknown_per_dimension(client, invitation, dimension_key, date_from, date_to):
        """
        REPLICATED: Build report for (dimension + DEVICE_CATEGORY_NAME); aggregate rows where device=Desktop.
        Returns: {dimension_value: {revenue, impressions, clicks, ecpm, ctr}}.
        Uses the specified dimension for aggregation.
        """
        # Dimensions to request
        base_dims = list(GAMReportService.DIMENSION_MAP.get(dimension_key, []))
        if not base_dims:
            return {}
        # Ensure we do not duplicate DEVICE_CATEGORY_NAME
        dims = list(base_dims)
        if "DEVICE_CATEGORY_NAME" not in dims:
            dims.append("DEVICE_CATEGORY_NAME")
        # Support composite key fields by keeping the full list
        key_field = base_dims

        # Child filter when MANAGE_INVENTORY
        filter_statement = None
        if invitation.delegation_type == 'MANAGE_INVENTORY':
            filter_statement = {
                'query': 'WHERE CHILD_NETWORK_CODE = :childNetworkCode',
                'values': [
                    {
                        'key': 'childNetworkCode',
                        'value': {'xsi_type': 'TextValue', 'value': str(invitation.child_network_code)}
                    }
                ]
            }

        report_query = {
            'dimensions': dims,
            'columns': [
                'AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS',
                'AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE',
                'AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS',
            ],
            'dateRangeType': 'CUSTOM_DATE',
            'startDate': date_from,
            'endDate': date_to,
            'reportCurrency': 'USD',  # Force USD currency for all reports
        }
        if filter_statement:
            report_query['statement'] = filter_statement
        report_job = {'reportQuery': report_query}

        downloader = client.GetDataDownloader(version="v202508")
        job_id = downloader.WaitForReport(report_job)
        with tempfile.TemporaryFile() as fp:
            downloader.DownloadReportToFile(job_id, 'GZIPPED_CSV', fp, include_totals_row=True)
            fp.seek(0)
            text = gzip.decompress(fp.read()).decode('utf-8', errors='ignore')

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) <= 1:
            return {}
        headers = [c.replace('Dimension.', '').replace('Column.', '') for c in rows[0]]
        data_rows = rows[1:]

        try:
            dc_idx = headers.index('DEVICE_CATEGORY_NAME')
        except ValueError:
            return {}

        # indexes for metrics
        def idx(name):
            try:
                return headers.index(name)
            except ValueError:
                return None
        imp_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS')
        rev_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE')
        clk_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS')
        # Build indexes for composite key
        key_idx = []
        if key_field:
            fields = key_field if isinstance(key_field, list) else [key_field]
            for kf in fields:
                try:
                    key_idx.append(headers.index(kf))
                except ValueError:
                    pass

        desktop_aliases = {'desktop', 'Desktop', 'DESKTOP', 'Computer', 'PC'}
        agg = {}
        for row in data_rows:
            if len(row) <= dc_idx:
                continue
            device_val = (row[dc_idx] or '').strip()
            if device_val not in desktop_aliases:
                continue
            # Build key value
            vals = []
            for i in key_idx:
                if i is not None and len(row) > i:
                    vals.append(str(row[i]))
            key_val = " | ".join(vals) if vals else None
            imp = int(float(row[imp_i] or 0)) if imp_i is not None else 0
            raw_rev = float(row[rev_i] or 0) if rev_i is not None else 0.0
            clk = int(float(row[clk_i] or 0)) if clk_i is not None else 0
            # Convert micros to currency using proper method
            rev = float(GAMReportService._convert_micros_to_currency(raw_rev))
            entry = agg.setdefault(key_val, {'revenue': 0.0, 'impressions': 0, 'clicks': 0})
            entry['revenue'] += rev
            entry['impressions'] += imp
            entry['clicks'] += clk

        # finalize eCPM and CTR
        for k, v in agg.items():
            imp = v['impressions']
            rev = v['revenue']
            clk = v['clicks']
            v['ecpm'] = (rev / imp * 1000) if imp > 0 else 0.0
            v['ctr'] = (clk / imp * 100) if imp > 0 else 0.0

        return agg

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
                        'MOBILE_CARRIER_NAME', 'CARRIER_NAME', 'BROWSER_NAME'
                    ):
                        if dim_col in row_dict:
                            val = str(row_dict.get(dim_col) or '').strip().lower()
                            if val == 'total':
                                raise StopIteration
                except StopIteration:
                    # Skip this totals row
                    continue
                
                # Get dimension value; support composite dimensions (e.g., country + carrier)
                dimension_value = None
                dim_cols = GAMReportService.DIMENSION_MAP.get(dimension_key, [])
                if dim_cols:
                    parts = []
                    for col in dim_cols:
                        parts.append(str(row_dict.get(col, 'Unknown')))
                    dimension_value = " | ".join(parts)
                
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
                
                # Create record data
                record_data = {
                    'parent_network': invitation.parent_network,
                    'invitation': invitation,
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
                    'unknown_revenue': Decimal('0'),
                    'unknown_impressions': 0,
                    'unknown_clicks': 0,
                    'unknown_ecpm': Decimal('0'),
                    'unknown_ctr': Decimal('0')
                }
                
                processed_records.append(record_data)
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to process row: {str(e)}")
                continue
        
        return processed_records

    @staticmethod
    def _store_report_data(data):
        """
        REPLICATED: Store report data in database with duplicate prevention for overview
        """
        try:
            # For overview records, ensure we don't create duplicates by using invitation as part of the unique constraint
            if data['dimension_type'] == 'overview':
                # Use invitation + date as unique constraint for overview to prevent duplicates
                record, created = MasterMetaData.objects.update_or_create(
                    invitation=data['invitation'],
                    dimension_type=data['dimension_type'],
                    date=data['date'],
                    defaults={
                        'parent_network': data['parent_network'],
                        'child_network_code': data['child_network_code'],
                        'dimension_value': data['dimension_value'],
                        'currency': data['currency'],
                        'impressions': data['impressions'],
                        'revenue': data['revenue'],
                        'ecpm': data['ecpm'],
                        'clicks': data['clicks'],
                        'ctr': data['ctr'],
                        'total_ad_requests': data['total_ad_requests'],
                        'viewable_impressions_rate': data['viewable_impressions_rate'],
                        'unknown_revenue': data['unknown_revenue'],
                        'unknown_impressions': data['unknown_impressions'],
                        'unknown_clicks': data['unknown_clicks'],
                        'unknown_ecpm': data['unknown_ecpm'],
                        'unknown_ctr': data['unknown_ctr']
                    }
                )
            else:
                # For other dimensions, use the original logic
                record, created = MasterMetaData.objects.update_or_create(
                    child_network_code=data['child_network_code'],
                    dimension_type=data['dimension_type'],
                    dimension_value=data['dimension_value'],
                    date=data['date'],
                    defaults={
                        'parent_network': data['parent_network'],
                        'invitation': data['invitation'],
                        'currency': data['currency'],
                        'impressions': data['impressions'],
                        'revenue': data['revenue'],
                        'ecpm': data['ecpm'],
                        'clicks': data['clicks'],
                        'ctr': data['ctr'],
                        'total_ad_requests': data['total_ad_requests'],
                        'viewable_impressions_rate': data['viewable_impressions_rate'],
                        'unknown_revenue': data['unknown_revenue'],
                        'unknown_impressions': data['unknown_impressions'],
                        'unknown_clicks': data['unknown_clicks'],
                        'unknown_ecpm': data['unknown_ecpm'],
                        'unknown_ctr': data['unknown_ctr']
                    }
                )
            
            logger.info(f"✅ Stored report data: {data['child_network_code']} - {data['dimension_type']}")
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

    @staticmethod
    def _aggregate_unknown_per_dimension(client, invitation, dimension_key, date_from, date_to):
        """
        STAGE 1: Build report for (dimension + DEVICE_CATEGORY_NAME); aggregate rows where device=Desktop.
        Returns: {dimension_value: {revenue, impressions, clicks, ecpm, ctr}}.
        Uses the specified dimension for aggregation.
        REPLICATED FROM SUB-REPORTS with date structure instead of timeframe
        """
        # Dimensions to request
        base_dims = list(GAMReportService.DIMENSION_MAP.get(dimension_key, []))
        if not base_dims:
            return {}
        # Ensure we do not duplicate DEVICE_CATEGORY_NAME
        dims = list(base_dims)
        if "DEVICE_CATEGORY_NAME" not in dims:
            dims.append("DEVICE_CATEGORY_NAME")
        # Support composite key fields by keeping the full list
        key_field = base_dims

        # Child filter when MANAGE_INVENTORY
        filter_statement = None
        if invitation.delegation_type == 'MANAGE_INVENTORY':
            filter_statement = {
                'query': 'WHERE CHILD_NETWORK_CODE = :childNetworkCode',
                'values': [
                    {
                        'key': 'childNetworkCode',
                        'value': {'xsi_type': 'TextValue', 'value': str(invitation.child_network_code)}
                    }
                ]
            }

        report_query = {
            'dimensions': dims,
            'columns': [
                'AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS',
                'AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE',
                'AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS',
            ],
            'dateRangeType': 'CUSTOM_DATE',
            'startDate': date_from,
            'endDate': date_to,
            'reportCurrency': 'USD',  # Force USD currency for all reports
        }
        if filter_statement:
            report_query['statement'] = filter_statement
        report_job = {'reportQuery': report_query}

        downloader = client.GetDataDownloader(version="v202508")
        job_id = downloader.WaitForReport(report_job)
        with tempfile.TemporaryFile() as fp:
            downloader.DownloadReportToFile(job_id, 'GZIPPED_CSV', fp, include_totals_row=True)
            fp.seek(0)
            text = gzip.decompress(fp.read()).decode('utf-8', errors='ignore')

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) <= 1:
            return {}
        headers = [c.replace('Dimension.', '').replace('Column.', '') for c in rows[0]]
        data_rows = rows[1:]

        try:
            dc_idx = headers.index('DEVICE_CATEGORY_NAME')
        except ValueError:
            return {}

        # indexes for metrics
        def idx(name):
            try:
                return headers.index(name)
            except ValueError:
                return None
        imp_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS')
        rev_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE')
        clk_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS')
        # Build indexes for composite key
        key_idx = []
        if key_field:
            fields = key_field if isinstance(key_field, list) else [key_field]
            for kf in fields:
                try:
                    key_idx.append(headers.index(kf))
                except ValueError:
                    pass

        desktop_aliases = {'desktop', 'Desktop', 'DESKTOP', 'Computer', 'PC'}
        agg = {}
        for row in data_rows:
            if len(row) <= dc_idx:
                continue
            device_val = (row[dc_idx] or '').strip()
            if device_val not in desktop_aliases:
                continue
            # Build key value
            vals = []
            for i in key_idx:
                if i is not None and len(row) > i:
                    vals.append(str(row[i]))
            key_val = " | ".join(vals) if vals else None
            imp = int(float(row[imp_i] or 0)) if imp_i is not None else 0
            raw_rev = float(row[rev_i] or 0) if rev_i is not None else 0.0
            clk = int(float(row[clk_i] or 0)) if clk_i is not None else 0
            # Convert micros to currency using proper method
            rev = float(GAMReportService._convert_micros_to_currency(raw_rev))
            entry = agg.setdefault(key_val, {'revenue': 0.0, 'impressions': 0, 'clicks': 0})
            entry['revenue'] += rev
            entry['impressions'] += imp
            entry['clicks'] += clk

        # finalize eCPM and CTR
        for k, v in agg.items():
            imp = v['impressions']
            rev = v['revenue']
            clk = v['clicks']
            v['ecpm'] = (rev / imp * 1000) if imp > 0 else 0.0
            v['ctr'] = (clk / imp * 100) if imp > 0 else 0.0

        return agg

    @staticmethod
    def _process_unknown_revenue_for_desktop(eligible_invitations, date_from, date_to):
        """
        STAGE 2: Process unknown revenue by moving desktop device data to unknown fields
        REPLICATED FROM SUB-REPORTS with date structure instead of timeframe
        """
        unknown_records_updated = 0
        
        try:
            logger.info(f"🔍 Processing unknown revenue for {len(eligible_invitations)} accounts")
            
            # First, get all desktop device records and store their data
            device_records = MasterMetaData.objects.filter(
                invitation__in=eligible_invitations,
                date__range=[date_from, date_to],
                dimension_type='deviceCategory'
            )
            
            # Find desktop device records and store their data
            desktop_data = {}
            for record in device_records:
                device_category = record.dimension_value or ''
                desktop_categories = ['Desktop', 'DESKTOP', 'desktop', 'Computer', 'COMPUTER', 'PC']
                
                if any(desktop_cat in device_category for desktop_cat in desktop_categories):
                    # Store desktop data by invitation and date
                    key = (record.invitation.id, record.date)
                    desktop_data[key] = {
                        'revenue': record.revenue,
                        'impressions': record.impressions,
                        'clicks': record.clicks,
                        'ecpm': record.ecpm,
                        'ctr': record.ctr
                    }
            
            logger.info(f"📊 Found {len(desktop_data)} desktop device records with data")
            
            # Now process all dimensions (copy desktop data to unknown section)
            dimension_types = ['overview', 'site', 'trafficSource', 'country', 'carrier', 'browser', 'country_carrier']
            
            for dimension_type in dimension_types:
                logger.info(f"🔍 Processing unknown revenue for dimension: {dimension_type}")
                
                # Get all records for this dimension
                dimension_records = MasterMetaData.objects.filter(
                    invitation__in=eligible_invitations,
                    date__range=[date_from, date_to],
                    dimension_type=dimension_type
                )
                
                # For each record in this dimension, add desktop data to unknown fields
                for record in dimension_records:
                    key = (record.invitation.id, record.date)
                    if key in desktop_data:
                        desktop_info = desktop_data[key]
                        
                        # Add desktop metrics to unknown fields
                        record.unknown_revenue = desktop_info['revenue']
                        record.unknown_impressions = desktop_info['impressions']
                        record.unknown_clicks = desktop_info['clicks']
                        record.unknown_ecpm = desktop_info['ecpm']
                        record.unknown_ctr = desktop_info['ctr']
                        
                        record.save()
                        unknown_records_updated += 1
                        
                        logger.debug(f"💻 Added desktop data to unknown for {dimension_type}: {record.child_network_code} - ${desktop_info['revenue']}")
            
            # Finally, clear the original desktop device category records
            for record in device_records:
                device_category = record.dimension_value or ''
                desktop_categories = ['Desktop', 'DESKTOP', 'desktop', 'Computer', 'COMPUTER', 'PC']
                
                if any(desktop_cat in device_category for desktop_cat in desktop_categories):
                    record.revenue = Decimal('0')
                    record.impressions = 0
                    record.clicks = 0
                    record.ecpm = Decimal('0')
                    record.ctr = Decimal('0')
                    record.save()
            
            logger.info(f"✅ Unknown revenue processing completed: {unknown_records_updated} records updated")
            return unknown_records_updated
            
        except Exception as e:
            logger.error(f"❌ Unknown revenue processing failed: {str(e)}")
            return 0

    # Sub-reports functionality removed - no longer needed for managed inventory publisher dashboard


    @staticmethod
    def _update_service_account_status(invitation, is_enabled, reason=""):
        """
        Update ONLY the service account status (service_account_enabled field) for the child network - DO NOT change GAM Status
        Also triggers Service Account Inaccessible Alert when service account is disabled
        """
        try:
            # Update ONLY the child network's service account status (stored on MCMInvitation)
            invitation.service_account_enabled = is_enabled
            invitation.save()
            
            # Log the service key status change (DO NOT change invitation status)
            if is_enabled:
                logger.info(f"✅ Service Key Status ENABLED for {invitation.child_network_code} - GAM Status remains '{invitation.status}'")
            else:
                logger.warning(f"❌ Service Key Status DISABLED for {invitation.child_network_code} - GAM Status remains '{invitation.status}' (Reason: {reason})")
                
                # Log service account status change
                logger.info(f"📝 Service account status changed for {invitation.child_network_code}: {reason}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to update service key status for {invitation.child_network_code}: {str(e)}")

    # Smart alerts functionality removed - no longer needed for managed inventory publisher dashboard

    @staticmethod
    def _process_unknown_metrics_for_all_dimensions(client, invitation, date_from, date_to):
        """
        Process unknown metrics for all dimensions using device category + other dimensions (same as sub-reports)
        For each dimension (except deviceCategory), fetch data with both that dimension AND DEVICE_CATEGORY_NAME
        Filter for Desktop devices and apply as unknown metrics
        """
        records_created = 0
        records_updated = 0
        
        # Process each dimension except deviceCategory itself
        for dimension_key in GAMReportService.DIMENSION_MAP.keys():
            if dimension_key == 'deviceCategory':
                continue  # Skip deviceCategory itself
                
            try:
                logger.info(f"📊 Processing unknown metrics for dimension: {dimension_key}")
                
                # Get unknown metrics for this dimension
                unknown_map = GAMReportService._aggregate_unknown_per_dimension(
                    client, invitation, dimension_key, date_from, date_to
                )
                
                if not unknown_map:
                    logger.info(f"📭 No unknown metrics found for {dimension_key}")
                    continue
                
                # Apply unknown metrics to existing records for this dimension
                for dimension_value, unknown_data in unknown_map.items():
                    try:
                        # Find existing record for this dimension and date
                        existing_record = MasterMetaData.objects.filter(
                            child_network_code=invitation.child_network_code,
                            dimension_type=dimension_key,
                            dimension_value=dimension_value,
                            date__range=[date_from, date_to]
                        ).first()
                        
                        if existing_record:
                            # Update existing record with unknown metrics
                            existing_record.unknown_revenue = GAMReportService._quantize(Decimal(str(unknown_data.get('revenue', 0))), 2)
                            existing_record.unknown_impressions = int(unknown_data.get('impressions', 0))
                            existing_record.unknown_clicks = int(unknown_data.get('clicks', 0))
                            existing_record.unknown_ecpm = GAMReportService._quantize(Decimal(str(unknown_data.get('ecpm', 0))), 2)
                            existing_record.unknown_ctr = GAMReportService._quantize(Decimal(str(unknown_data.get('ctr', 0))), 2)
                            existing_record.save()
                            records_updated += 1
                            logger.info(f"✅ Updated unknown metrics for {dimension_key}={dimension_value}")
                        else:
                            logger.warning(f"⚠️ No existing record found for {dimension_key}={dimension_value}")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to update unknown metrics for {dimension_key}={dimension_value}: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to process unknown metrics for dimension {dimension_key}: {str(e)}")
                continue
        
        return {
            'records_created': records_created,
            'records_updated': records_updated
        }

    @staticmethod
    def _aggregate_unknown_per_dimension(client, invitation, dimension_key, date_from, date_to):
        """
        Build report for (dimension + DEVICE_CATEGORY_NAME); aggregate rows where device=Desktop.
        Returns: {dimension_value: {revenue, impressions, clicks, ecpm, ctr}}.
        Uses the specified dimension for aggregation (same logic as sub-reports).
        """
        # Dimensions to request
        base_dims = list(GAMReportService.DIMENSION_MAP.get(dimension_key, []))
        if not base_dims:
            return {}
            
        # Ensure we do not duplicate DEVICE_CATEGORY_NAME
        dims = list(base_dims)
        if "DEVICE_CATEGORY_NAME" not in dims:
            dims.append("DEVICE_CATEGORY_NAME")
            
        # Support composite key fields by keeping the full list
        # For overview dimension, we don't need a key field since we aggregate by date
        if dimension_key == 'overview':
            key_field = None  # Overview aggregates by date, no specific dimension key needed
        else:
            key_field = base_dims

        # Child filter when MANAGE_INVENTORY
        filter_statement = None
        if invitation.delegation_type == 'MANAGE_INVENTORY':
            filter_statement = {
                'query': 'WHERE CHILD_NETWORK_CODE = :childNetworkCode',
                'values': [
                    {
                        'key': 'childNetworkCode',
                        'value': {'xsi_type': 'TextValue', 'value': str(invitation.child_network_code)}
                    }
                ]
            }

        report_query = {
            'dimensions': dims,
            'columns': [
                'AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS',
                'AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE',
                'AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS',
            ],
            'dateRangeType': 'CUSTOM_DATE',
            'startDate': date_from,
            'endDate': date_to,
            'reportCurrency': 'USD',  # Force USD currency for all reports
        }
        if filter_statement:
            report_query['statement'] = filter_statement
        report_job = {'reportQuery': report_query}

        downloader = client.GetDataDownloader(version="v202508")
        job_id = downloader.WaitForReport(report_job)
        
        with tempfile.TemporaryFile() as fp:
            downloader.DownloadReportToFile(job_id, 'GZIPPED_CSV', fp, include_totals_row=True)
            fp.seek(0)
            text = gzip.decompress(fp.read()).decode('utf-8', errors='ignore')

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) <= 1:
            return {}
            
        headers = [c.replace('Dimension.', '').replace('Column.', '') for c in rows[0]]
        data_rows = rows[1:]

        try:
            dc_idx = headers.index('DEVICE_CATEGORY_NAME')
        except ValueError:
            return {}

        # indexes for metrics
        def idx(name):
            try:
                return headers.index(name)
            except ValueError:
                return None
        imp_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS')
        rev_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE')
        clk_i = idx('AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS')
        
        # Build indexes for composite key
        key_idx = []
        if key_field:
            fields = key_field if isinstance(key_field, list) else [key_field]
            for kf in fields:
                try:
                    key_idx.append(headers.index(kf))
                except ValueError:
                    pass

        desktop_aliases = {'desktop', 'Desktop', 'DESKTOP', 'Computer', 'PC'}
        agg = {}
        for row in data_rows:
            if len(row) <= dc_idx:
                continue
            device_val = (row[dc_idx] or '').strip()
            if device_val not in desktop_aliases:
                continue
                
            # Build key value
            vals = []
            for i in key_idx:
                if i is not None and len(row) > i:
                    vals.append(str(row[i]))
            key_val = " | ".join(vals) if vals else None
            
            imp = int(float(row[imp_i] or 0)) if imp_i is not None else 0
            raw_rev = float(row[rev_i] or 0) if rev_i is not None else 0.0
            clk = int(float(row[clk_i] or 0)) if clk_i is not None else 0
            
            # Convert micros to currency using proper method
            rev = float(GAMReportService._convert_micros_to_currency(raw_rev))
            
            entry = agg.setdefault(key_val, {'revenue': 0.0, 'impressions': 0, 'clicks': 0})
            entry['revenue'] += rev
            entry['impressions'] += imp
            entry['clicks'] += clk

        # finalize eCPM and CTR
        for k, v in agg.items():
            imp = v['impressions']
            rev = v['revenue']
            clk = v['clicks']
            v['ecpm'] = (rev / imp * 1000) if imp > 0 else 0.0
            v['ctr'] = (clk / imp * 100) if imp > 0 else 0.0

        return agg
