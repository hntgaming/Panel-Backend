import os
import django
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime, timedelta
import logging
import concurrent.futures
import time
import threading

from django.conf import settings
from django.core.mail import send_mail

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'multigam.settings')
django.setup()

from reports.services import GAMReportService

logger = logging.getLogger(__name__)

# ============================================================================
# OPTIMIZED PARALLEL PROCESSING SETTINGS
# ============================================================================
# Google Ad Manager API: 2 requests/second PER ACCOUNT (not global!)
# This means each account has independent quota
# We can process ALL accounts in parallel without global throttling
# ============================================================================

# No global rate limiting needed - each account has independent quota
QUOTA_RETRY_DELAY = 5  # Seconds to wait when individual account quota exceeded
MAX_QUOTA_RETRIES = 5  # Retries per account

# Maximum parallelism - process ALL accounts simultaneously
DEFAULT_PARALLEL_ENABLED = True
DEFAULT_MAX_WORKERS = 500  # High worker count for true parallelism


class Command(BaseCommand):
    help = 'Fetch GAM reports for all eligible publisher networks - OPTIMIZED PARALLEL VERSION'

    def __init__(self):
        super().__init__()
        self._worker_lock = threading.Lock()
        self._active_workers = 0
        self._completed_count = 0
        self._total_accounts = 0

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
            dest='parallel',
            action='store_true',
            default=DEFAULT_PARALLEL_ENABLED,
            help=f'Enable parallel processing (default: {DEFAULT_PARALLEL_ENABLED})',
        )
        parser.add_argument(
            '--no-parallel',
            dest='parallel',
            action='store_false',
            help='Disable parallel processing for this run',
        )
        parser.add_argument(
            '--max-workers',
            type=int,
            default=DEFAULT_MAX_WORKERS,
            help=f'Maximum number of parallel workers (default: {DEFAULT_MAX_WORKERS})',
        )
        parser.add_argument(
            '--network-id',
            type=str,
            help='Process only specific network ID (for targeted fetching)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting GAM reports fetch (OPTIMIZED PARALLEL MODE)...')
        )
        
        # Parse dates
        date_from = options.get('date_from')
        date_to = options.get('date_to')
        parallel = options.get('parallel', DEFAULT_PARALLEL_ENABLED)
        max_workers = options.get('max_workers', DEFAULT_MAX_WORKERS)
        network_id = options.get('network_id')
        
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
        parallel_status = 'enabled' if parallel else 'disabled'
        self.stdout.write(f'⚡ Parallel processing {parallel_status}; max workers: {max_workers}')
        self.stdout.write(f'🔓 NO GLOBAL THROTTLING - Each account has independent 2 req/sec quota')
        
        if network_id:
            self.stdout.write(f'🎯 Targeting specific network: {network_id}')
        
        try:
            # Process GAM reports
            if parallel:
                result = self._process_all_parallel(
                    date_from, date_to, max_workers, network_id
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
                    self.style.ERROR(f'❌ GAM Reports Sync failed: {result.get("error", "Unknown error")}')
                )
        
        except Exception as e:
            logger.error(f'Command execution failed: {str(e)}', exc_info=True)
            self.stdout.write(
                self.style.ERROR(f'💥 Critical error: {str(e)}')
            )
            raise CommandError(f'Report fetch failed: {str(e)}')

    def _process_all_parallel(self, date_from, date_to, max_workers, network_id=None):
        """
        Process ALL accounts in TRUE PARALLEL - no global throttling!
        Each account has its own independent API quota (2 req/sec per account).
        Optimized parallel processing for maximum efficiency.
        """
        from accounts.models import User
        from core.models import StatusChoices
        from itertools import chain
        
        mcm_publishers = User.objects.filter(
            role=User.UserRole.PUBLISHER,
            status=StatusChoices.ACTIVE,
            gam_type='mcm',
            network_id__isnull=False
        ).exclude(network_id='')
        
        oo_publishers = User.objects.filter(
            role=User.UserRole.PUBLISHER,
            status=StatusChoices.ACTIVE,
            gam_type='o_and_o',
            site_url__isnull=False
        ).exclude(site_url='')
        
        if network_id:
            mcm_publishers = mcm_publishers.filter(network_id=network_id)
            oo_publishers = oo_publishers.none()
        
        publisher_list = list(chain(mcm_publishers, oo_publishers))
        self._total_accounts = len(publisher_list)
        self._completed_count = 0
        
        self.stdout.write(
            self.style.SUCCESS(
                f'📊 Found {self._total_accounts} eligible publisher accounts\n'
                f'🚀 Processing ALL accounts in parallel (no throttling!)\n'
                f'💡 Theoretical capacity: {self._total_accounts * 2} requests/second'
            )
        )
        
        if self._total_accounts == 0:
            return {
                'success': True,
                'sync_id': 'no-accounts',
                'successful_networks': 0,
                'failed_networks': 0,
                'total_records_created': 0,
                'total_records_updated': 0
            }
        
        start_time = time.time()
        results = []
        
        # Use workers = min(max_workers, total_accounts) for efficiency
        actual_workers = min(max_workers, self._total_accounts)
        self.stdout.write(
            f'🧵 Spawning {actual_workers} worker threads for {self._total_accounts} accounts'
        )
        
        # Process ALL accounts in parallel - submit each account as individual task
        with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
            # Submit ALL accounts at once - no batching, no throttling
            future_to_publisher = {
                executor.submit(
                    self._process_single_account, 
                    publisher, 
                    date_from, 
                    date_to
                ): publisher 
                for publisher in publisher_list
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_publisher):
                publisher = future_to_publisher[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update progress
                    with self._worker_lock:
                        self._completed_count += 1
                        if self._completed_count % 10 == 0 or self._completed_count == self._total_accounts:
                            elapsed = time.time() - start_time
                            rate = self._completed_count / elapsed if elapsed > 0 else 0
                            self.stdout.write(
                                f'📊 Progress: {self._completed_count}/{self._total_accounts} '
                                f'({self._completed_count * 100 // self._total_accounts}%) - '
                                f'{rate:.1f} accounts/sec'
                            )
                    
                except Exception as e:
                    acct_label = publisher.network_id or publisher.site_url or publisher.email
                    self.stdout.write(
                        self.style.ERROR(f'❌ {acct_label}: {str(e)}')
                    )
                    results.append({
                        'account': acct_label,
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
        
        # Final summary
        accounts_per_sec = self._total_accounts / duration if duration > 0 else 0
        self.stdout.write(
            self.style.SUCCESS(
                f'\n{"="*60}\n'
                f'⚡ PARALLEL PROCESSING COMPLETE\n'
                f'{"="*60}\n'
                f'⏱️  Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)\n'
                f'📈 Accounts processed: {self._total_accounts}\n'
                f'✅ Successful: {successful}\n'
                f'❌ Failed: {failed}\n'
                f'📊 Records created: {total_records}\n'
                f'🚀 Speed: {accounts_per_sec:.1f} accounts/second\n'
                f'{"="*60}'
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

    def _process_single_account(self, publisher, date_from, date_to):
        """
        Process a single account with retry logic.
        NO global throttling - each account has independent quota.
        """
        account_code = publisher.network_id or publisher.site_url or publisher.email
        
        for attempt in range(MAX_QUOTA_RETRIES):
            try:
                result = GAMReportService._process_publisher_network(
                    publisher, date_from, date_to
                )
                
                return {
                    'account': account_code,
                    'success': True,
                    'records_created': result.get('records_created', 0),
                    'records_updated': result.get('records_updated', 0)
                }
                
            except Exception as e:
                error_message = str(e)
                
                # Check if it's a quota error - retry with backoff
                if any(keyword in error_message.upper() for keyword in [
                    'EXCEEDED_QUOTA', 'QUOTA_ERROR', 'QUOTA_EXCEEDED', 'RATE_LIMIT'
                ]):
                    if attempt < MAX_QUOTA_RETRIES - 1:
                        wait_time = QUOTA_RETRY_DELAY * (2 ** attempt)
                        self.stdout.write(
                            self.style.WARNING(
                                f'⚠️ {account_code}: Quota hit, retry {attempt + 1}/{MAX_QUOTA_RETRIES} in {wait_time}s'
                            )
                        )
                        time.sleep(wait_time)
                        continue
                
                # Check if it's a service key error (auth error)
                is_auth_error = any(keyword in error_message.lower() for keyword in [
                    'service_account', 'authentication', 'unauthorized', 'forbidden',
                    'invalid credentials', 'access denied', 'no networks to access'
                ])
                
                return {
                    'account': account_code,
                    'success': False,
                    'error': error_message,
                    'records_created': 0,
                    'is_auth_error': is_auth_error
                }
        
        # Exhausted retries
        return {
            'account': account_code,
            'success': False,
            'error': f'Quota exceeded after {MAX_QUOTA_RETRIES} retries',
            'records_created': 0,
            'is_auth_error': False
        }

    @classmethod
    def handle_cronjob(cls):
        """Enhanced cron job execution with monitoring and recovery"""
        start_time = timezone.now()
        log_file = '/tmp/gam_reports_cron.log'

        try:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file, mode='a'),
                    logging.StreamHandler()
                ]
            )

            logger.info('🚀 Starting automated GAM report fetch via cron (OPTIMIZED)')
            logger.info(f'📅 Start time: {start_time}')

            command = cls()
            command.handle(
                date_from=None,
                date_to=None,
                days_back=1,
                parallel=True,
                max_workers=500,  # High parallelism
            )

            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(f'✅ Cron completed in {duration:.2f} seconds')
            cls._cleanup_old_logs()

        except Exception as e:
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            logger.error(f'❌ Cron failed after {duration:.2f}s: {str(e)}', exc_info=True)
            cls._send_failure_alert(str(e), duration)
            raise

    @classmethod
    def _cleanup_old_logs(cls):
        """Clean up old log files"""
        import glob

        try:
            log_pattern = '/tmp/gam_reports_cron*.log'
            log_files = glob.glob(log_pattern)
            cutoff_time = time.time() - (7 * 24 * 60 * 60)

            for log_file in log_files:
                if os.path.getmtime(log_file) < cutoff_time:
                    os.remove(log_file)
                    logger.info(f'🗑️ Cleaned up: {log_file}')

        except Exception as e:
            logger.warning(f'Failed to cleanup logs: {e}')

    @classmethod
    def _send_failure_alert(cls, error_message, duration):
        """Send failure alert email if configured"""
        try:
            if hasattr(settings, 'EMAIL_HOST_USER') and settings.EMAIL_HOST_USER:
                send_mail(
                    'GAM Reports Cron Job Failed',
                    f'Error: {error_message}\nDuration: {duration:.2f}s\nTime: {timezone.now()}',
                    settings.EMAIL_HOST_USER,
                    [settings.EMAIL_HOST_USER],
                    fail_silently=True
                )
                logger.info('📧 Failure alert sent')
        except Exception as e:
            logger.warning(f'Failed to send alert: {e}')
