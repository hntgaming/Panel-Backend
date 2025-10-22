from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime, timedelta
import logging
import concurrent.futures
import time

from reports.services import GAMReportService
# Removed gam_accounts dependencies

logger = logging.getLogger(__name__)

# Google Ad Manager API Quota Settings
# For Ad Manager accounts (not 360): 2 requests per second limit
# For Ad Manager 360 accounts: 8 requests per second limit
# We're using Ad Manager accounts, so 2 requests per second
API_REQUESTS_PER_SECOND = 2
REQUEST_DELAY = 1.0 / API_REQUESTS_PER_SECOND  # 0.5 seconds between requests
MAX_CONCURRENT_REQUESTS = 2  # Maximum concurrent API requests
QUOTA_RETRY_DELAY = 10  # Seconds to wait when quota exceeded
MAX_QUOTA_RETRIES = 3


class Command(BaseCommand):
    help = 'Fetch GAM reports for all eligible child networks with corrected GAM API mappings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date-from',
            type=str,
            help='Start date (YYYY-MM-DD format)',
        )
        parser.add_argument(
            '--date-to', 
            type=str,
            help='End date (YYYY-MM-DD format)',
        )
        parser.add_argument(
            '--days-back',
            type=int,
            default=0,
            help='Number of days back from today (default: 0 for today)',
        )
        parser.add_argument(
            '--parallel',
            action='store_true',
            default=True,
            help='Enable parallel processing for all accounts (default: True)',
        )
        parser.add_argument(
            '--max-workers',
            type=int,
            default=MAX_CONCURRENT_REQUESTS,
            help=f'Maximum number of parallel workers (default: {MAX_CONCURRENT_REQUESTS} - API quota compliant)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=93,
            help='Number of accounts to process in each batch (default: 93 for all accounts)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting GAM reports fetch...')
        )
        
        # Parse dates
        date_from = options.get('date_from')
        date_to = options.get('date_to')
        parallel = options.get('parallel', True)  # Default to True
        max_workers = options.get('max_workers', 100)
        batch_size = options.get('batch_size', 93)
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR('Invalid date_from format. Use YYYY-MM-DD')
                )
                return
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR('Invalid date_to format. Use YYYY-MM-DD')
                )
                return
        
        # Set defaults if not provided - DEFAULT TO TODAY
        if not date_to:
            date_to = timezone.now().date()
        
        if not date_from:
            days_back = options.get('days_back', 0)  # Default to 0 (today)
            date_from = date_to - timedelta(days=days_back)
        
        self.stdout.write(f'📅 Fetching reports from {date_from} to {date_to}')
        self.stdout.write(f'⚡ Parallel processing: {max_workers} workers (API quota compliant), batch size: {batch_size}')
        self.stdout.write(f'🕐 API Rate Limit: {API_REQUESTS_PER_SECOND} requests/second, {REQUEST_DELAY:.1f}s delay between requests')
        
        try:
            # Process GAM reports
            if parallel:
                result = self._process_parallel(
                    date_from, date_to, max_workers, batch_size
                )
            else:
                result = GAMReportService.fetch_gam_reports(
                    date_from=date_from,
                    date_to=date_to
                )
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ GAM Reports Sync completed successfully!\n'
                        f'   Sync ID: {result["sync_id"]}\n'
                        f'   Successful networks: {result["successful_networks"]}\n'
                        f'   Failed networks: {result["failed_networks"]}\n'
                        f'   Records created: {result["total_records_created"]}\n'
                        f'   Records updated: {result["total_records_updated"]}'
                    )
                )
                
            else:
                self.stdout.write(
                    self.style.ERROR(f'❌ GAM Reports Sync failed: {result["error"]}')
                )
        
        except Exception as e:
            logger.error(f'Command execution failed: {str(e)}', exc_info=True)
            self.stdout.write(
                self.style.ERROR(f'💥 Critical error: {str(e)}')
            )
            raise CommandError(f'Report fetch failed: {str(e)}')

    def _process_parallel(self, date_from, date_to, max_workers, batch_size):
        """Process all accounts in parallel"""
        # Get all active publisher users with network IDs
        from accounts.models import User
        eligible_publishers = User.objects.filter(
            role='publisher',
            is_active=True,
            network_id__isnull=False
        ).exclude(network_id='')
        
        total_accounts = eligible_publishers.count()
        self.stdout.write(f'📊 Found {total_accounts} eligible publisher accounts')
        
        if total_accounts == 0:
            return {
                'success': True,
                'sync_id': 'no-accounts',
                'successful_networks': 0,
                'failed_networks': 0,
                'total_records_created': 0,
                'total_records_updated': 0
            }
        
        # Split publishers into batches
        publisher_list = list(eligible_publishers)
        batches = [publisher_list[i:i + batch_size] for i in range(0, len(publisher_list), batch_size)]
        
        self.stdout.write(f'📦 Processing {len(batches)} batches of up to {batch_size} accounts each')
        
        start_time = time.time()
        results = []
        
        # Ensure max_workers doesn't exceed API quota
        actual_max_workers = min(max_workers, MAX_CONCURRENT_REQUESTS)
        if max_workers > MAX_CONCURRENT_REQUESTS:
            self.stdout.write(
                self.style.WARNING(f'⚠️ Reducing max_workers from {max_workers} to {actual_max_workers} to comply with API quota')
            )
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=actual_max_workers) as executor:
            # Submit all batches with API quota compliance
            future_to_batch = {
                executor.submit(self._process_batch_with_quota, batch, date_from, date_to): batch                                                                                                            
                for batch in batches
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_batch):
                batch = future_to_batch[future]
                try:
                    batch_results = future.result()
                    results.extend(batch_results)
                    
                    
                    # Log progress
                    completed = len(results)
                    self.stdout.write(f'📊 Progress: {completed}/{total_accounts} accounts processed')
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'❌ Batch processing failed: {str(e)}')
                    )
                    # Add failed results for this batch
                    for publisher in batch:
                        results.append({
                            'account': publisher.network_id,
                            'success': False,
                            'error': str(e),
                            'records_created': 0
                        })
        
        end_time = time.time()
        duration = end_time - start_time
        
        
        # Calculate summary
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        total_records = sum(r.get('records_created', 0) for r in results)
        
        # Process unknown revenue after all accounts are processed
        self.stdout.write('🔍 Processing unknown revenue for all accounts...')
        try:
            # Unknown revenue processing removed for Managed Inventory Publisher Dashboard
            self.stdout.write('✅ Report fetching completed (unknown metrics processing removed)')
        except Exception as e:
            self.stdout.write(f'❌ Unknown revenue processing failed: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'⚡ Parallel processing completed in {duration:.2f} seconds\n'
                f'📈 Results: {successful} successful, {failed} failed\n'
                f'📊 Total records created: {total_records}'
            )
        )
        
        return {
            'success': True,
            'sync_id': f'parallel-{int(time.time())}',
            'successful_networks': successful,
            'failed_networks': failed,
            'total_records_created': total_records,
            'total_records_updated': 0
        }

    def _process_batch_with_quota(self, batch, date_from, date_to):
        """Process a batch of publisher accounts with API quota compliance"""
        batch_results = []
        
        for i, publisher in enumerate(batch):
            try:
                # Add delay between requests to respect API quota
                if i > 0:  # Don't delay the first request
                    time.sleep(REQUEST_DELAY)
                
                self.stdout.write(f'🔄 Processing {publisher.network_id} ({publisher.email})...')
                
                # Process single account with quota retry logic
                result = self._process_account_with_quota_retry(
                    publisher, date_from, date_to
                )
                
                batch_results.append({
                    'account': publisher.network_id,
                    'success': True,
                    'records_created': result.get('records_created', 0),
                    'records_updated': result.get('records_updated', 0)
                })
                
                self.stdout.write(
                    f'✅ {publisher.network_id}: {result.get("records_created", 0)} records created'
                )
                
            except Exception as e:
                error_message = str(e)
                self.stdout.write(
                    self.style.ERROR(f'❌ {publisher.network_id}: {error_message}')
                )
                
                
                batch_results.append({
                    'account': publisher.network_id,
                    'success': False,
                    'error': error_message,
                    'records_created': 0,
                })
        
        return batch_results
    
    def _process_account_with_quota_retry(self, publisher, date_from, date_to):
        """Process single account with quota error retry logic"""
        for attempt in range(MAX_QUOTA_RETRIES):
            try:
                return GAMReportService._process_publisher_network(
                    publisher, date_from, date_to
                )
            except Exception as e:
                error_message = str(e)
                
                # Check if it's a quota error
                if any(keyword in error_message.upper() for keyword in [
                    'EXCEEDED_QUOTA', 'QUOTA_ERROR', 'QUOTA_EXCEEDED', 'RATE_LIMIT'
                ]):
                    if attempt < MAX_QUOTA_RETRIES - 1:
                        wait_time = QUOTA_RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                        self.stdout.write(
                            self.style.WARNING(
                                f'⚠️ Quota exceeded for {publisher.network_id}, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_QUOTA_RETRIES})'
                            )
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'❌ Quota exceeded for {publisher.network_id} after {MAX_QUOTA_RETRIES} attempts'
                            )
                        )
                
                # If it's not a quota error or we've exhausted retries, raise the exception
                raise e
    
    @classmethod
    def handle_cronjob(cls):
        """
        Enhanced cron job execution with monitoring and recovery
        """
        import os
        from django.core.mail import send_mail
        from django.conf import settings

        start_time = timezone.now()
        log_file = '/tmp/gam_reports_cron.log'

        try:
            # Set up enhanced logging for cron
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file, mode='a'),
                    logging.StreamHandler()
                ]
            )

            logger.info('🚀 Starting automated GAM report fetch via cron')
            logger.info(f'📅 Start time: {start_time}')
            logger.info(f'📝 Log file: {log_file}')

            # Check if another instance is running
            lock_file = '/tmp/gam_reports_cron.lock'
            if os.path.exists(lock_file):
                logger.warning('⚠️ Another cron job instance is already running. Skipping.')
                return

            # Create lock file
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))

            try:
                # Create command instance and execute with API quota compliance
                command = cls()
                command.handle(
                    date_from=None,  # Use defaults (last 1 day for frequent runs)
                    date_to=None,
                    days_back=1,
                    parallel=True,  # Enable parallel processing
                    max_workers=MAX_CONCURRENT_REQUESTS,  # API quota compliant
                    batch_size=50,  # Smaller batches for cron jobs
                )

                end_time = timezone.now()
                duration = (end_time - start_time).total_seconds()

                logger.info(f'✅ Automated GAM report fetch completed successfully')
                logger.info(f'⏱️ Duration: {duration:.2f} seconds')

                # Clean up old log files (keep last 7 days)
                cls._cleanup_old_logs()

            finally:
                # Remove lock file
                if os.path.exists(lock_file):
                    os.remove(lock_file)

        except Exception as e:
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()

            logger.error(f'❌ Cron job failed after {duration:.2f} seconds: {str(e)}', exc_info=True)

            # Send alert email if configured
            cls._send_failure_alert(str(e), duration)

            # Remove lock file on failure
            lock_file = '/tmp/gam_reports_cron.lock'
            if os.path.exists(lock_file):
                os.remove(lock_file)

            raise

    @classmethod
    def _cleanup_old_logs(cls):
        """Clean up old log files"""
        import glob
        import time

        try:
            log_pattern = '/tmp/gam_reports_cron*.log'
            log_files = glob.glob(log_pattern)

            # Keep files from last 7 days
            cutoff_time = time.time() - (7 * 24 * 60 * 60)

            for log_file in log_files:
                if os.path.getmtime(log_file) < cutoff_time:
                    os.remove(log_file)
                    logger.info(f'🗑️ Cleaned up old log file: {log_file}')

        except Exception as e:
            logger.warning(f'Failed to cleanup old logs: {e}')

    @classmethod
    def _send_failure_alert(cls, error_message, duration):
        """Send failure alert email if configured"""
        try:
            if hasattr(settings, 'EMAIL_HOST_USER') and settings.EMAIL_HOST_USER:
                admin_emails = [settings.EMAIL_HOST_USER]  # Or configure ADMIN_EMAILS

                subject = 'GAM Reports Cron Job Failed'
                message = f"""
GAM Reports cron job failed:

Error: {error_message}
Duration: {duration:.2f} seconds
Time: {timezone.now()}

Please check the logs for more details.
                """

                send_mail(
                    subject,
                    message,
                    settings.EMAIL_HOST_USER,
                    admin_emails,
                    fail_silently=True
                )

                logger.info('📧 Failure alert email sent')

        except Exception as e:
            logger.warning(f'Failed to send failure alert: {e}')
