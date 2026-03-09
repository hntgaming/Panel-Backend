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

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'multigam.settings')
django.setup()

from reports.services import GAMReportService
from reports.gam_client import GAMClientService

logger = logging.getLogger(__name__)

QUOTA_RETRY_DELAY = 5
MAX_QUOTA_RETRIES = 5
DEFAULT_PARALLEL_ENABLED = True
DEFAULT_MAX_WORKERS = 500


class Command(BaseCommand):
    help = 'Fetch GAM reports for all eligible publisher networks - OPTIMIZED PARALLEL VERSION'

    def __init__(self):
        super().__init__()
        self._worker_lock = threading.Lock()
        self._active_workers = 0
        self._completed_count = 0
        self._total_accounts = 0

    def add_arguments(self, parser):
        parser.add_argument('--date-from', type=str, help='Start date (YYYY-MM-DD)')
        parser.add_argument('--date-to', type=str, help='End date (YYYY-MM-DD)')
        parser.add_argument('--days-back', type=int, default=0, help='Days back from today (default: 0)')
        parser.add_argument('--parallel', dest='parallel', action='store_true', default=DEFAULT_PARALLEL_ENABLED)
        parser.add_argument('--no-parallel', dest='parallel', action='store_false')
        parser.add_argument('--max-workers', type=int, default=DEFAULT_MAX_WORKERS)
        parser.add_argument('--network-id', type=str, help='Process only specific network ID')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting GAM reports fetch (OPTIMIZED PARALLEL MODE)...'))

        date_from = options.get('date_from')
        date_to = options.get('date_to')
        parallel = options.get('parallel', DEFAULT_PARALLEL_ENABLED)
        max_workers = options.get('max_workers', DEFAULT_MAX_WORKERS)
        network_id = options.get('network_id')

        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date_from format. Use YYYY-MM-DD'))
                return

        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date_to format. Use YYYY-MM-DD'))
                return

        if not date_to:
            date_to = timezone.now().date()
        if not date_from:
            days_back = options.get('days_back', 0)
            date_from = date_to - timedelta(days=days_back)

        self.stdout.write(f'Date range: {date_from} to {date_to}')
        self.stdout.write(f'Parallel: {"on" if parallel else "off"} | Max workers: {max_workers}')

        if network_id:
            self.stdout.write(f'Targeting: {network_id}')

        # Clear cached GAM clients from previous runs
        GAMClientService.clear_client_cache()

        try:
            if parallel:
                result = self._process_all_parallel(date_from, date_to, max_workers, network_id)
            else:
                result = GAMReportService.fetch_gam_reports(date_from=date_from, date_to=date_to)

            if result['success']:
                self.stdout.write(self.style.SUCCESS(
                    f'Sync completed | ID: {result["sync_id"]} | '
                    f'OK: {result["successful_networks"]} | '
                    f'Fail: {result["failed_networks"]} | '
                    f'Created: {result["total_records_created"]} | '
                    f'Updated: {result["total_records_updated"]}'
                ))
            else:
                self.stdout.write(self.style.ERROR(f'Sync failed: {result.get("error")}'))

        except Exception as e:
            logger.error(f'Command execution failed: {e}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'Critical error: {e}'))
            raise CommandError(f'Report fetch failed: {e}')

    def _process_all_parallel(self, date_from, date_to, max_workers, network_id=None):
        from accounts.models import User
        from core.models import StatusChoices
        from itertools import chain

        mcm_qs = User.objects.filter(
            role=User.UserRole.PUBLISHER,
            status=StatusChoices.ACTIVE,
            gam_type='mcm',
            network_id__isnull=False,
        ).exclude(network_id='')

        oo_qs = User.objects.filter(
            role=User.UserRole.PUBLISHER,
            status=StatusChoices.ACTIVE,
            gam_type='o_and_o',
            site_url__isnull=False,
        ).exclude(site_url='')

        if network_id:
            mcm_qs = mcm_qs.filter(network_id=network_id)
            oo_qs = oo_qs.none()

        publisher_list = list(chain(mcm_qs, oo_qs))
        self._total_accounts = len(publisher_list)
        self._completed_count = 0

        self.stdout.write(self.style.SUCCESS(
            f'Found {self._total_accounts} eligible accounts | '
            f'MCM: {mcm_qs.count()} | O&O: {oo_qs.count()}'
        ))

        if self._total_accounts == 0:
            return {
                'success': True, 'sync_id': 'no-accounts',
                'successful_networks': 0, 'failed_networks': 0,
                'total_records_created': 0, 'total_records_updated': 0,
            }

        start_time = time.time()
        results = []
        actual_workers = min(max_workers, self._total_accounts)
        self.stdout.write(f'Spawning {actual_workers} workers for {self._total_accounts} accounts')

        with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
            future_to_pub = {
                executor.submit(self._process_single_account, pub, date_from, date_to): pub
                for pub in publisher_list
            }

            for future in concurrent.futures.as_completed(future_to_pub):
                publisher = future_to_pub[future]
                try:
                    result = future.result()
                    results.append(result)

                    with self._worker_lock:
                        self._completed_count += 1
                        if self._completed_count % 5 == 0 or self._completed_count == self._total_accounts:
                            elapsed = time.time() - start_time
                            rate = self._completed_count / elapsed if elapsed > 0 else 0
                            self.stdout.write(
                                f'Progress: {self._completed_count}/{self._total_accounts} '
                                f'({self._completed_count * 100 // self._total_accounts}%) - '
                                f'{rate:.1f} acct/s'
                            )
                except Exception as e:
                    label = publisher.network_id or publisher.site_url or publisher.email
                    self.stdout.write(self.style.ERROR(f'{label}: {e}'))
                    results.append({
                        'account': label, 'success': False,
                        'error': str(e), 'records_created': 0,
                    })

        duration = time.time() - start_time
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        total_records = sum(r.get('records_created', 0) for r in results)

        self.stdout.write(self.style.SUCCESS(
            f'\n{"=" * 60}\n'
            f'PARALLEL PROCESSING COMPLETE\n'
            f'{"=" * 60}\n'
            f'Duration: {duration:.1f}s ({duration / 60:.1f}m)\n'
            f'Accounts: {self._total_accounts} | OK: {successful} | Fail: {failed}\n'
            f'Records: {total_records} | Speed: {self._total_accounts / duration:.1f} acct/s\n'
            f'{"=" * 60}'
        ))

        return {
            'success': True,
            'sync_id': f'parallel-{int(time.time())}',
            'successful_networks': successful,
            'failed_networks': failed,
            'total_records_created': total_records,
            'total_records_updated': 0,
        }

    def _process_single_account(self, publisher, date_from, date_to):
        account_code = publisher.network_id or publisher.site_url or publisher.email

        for attempt in range(MAX_QUOTA_RETRIES):
            try:
                result = GAMReportService._process_publisher_network(publisher, date_from, date_to)
                return {
                    'account': account_code,
                    'success': True,
                    'records_created': result.get('records_created', 0),
                    'records_updated': result.get('records_updated', 0),
                }
            except Exception as e:
                error_message = str(e)

                if any(kw in error_message.upper() for kw in [
                    'EXCEEDED_QUOTA', 'QUOTA_ERROR', 'QUOTA_EXCEEDED', 'RATE_LIMIT',
                ]):
                    if attempt < MAX_QUOTA_RETRIES - 1:
                        wait = QUOTA_RETRY_DELAY * (2 ** attempt)
                        self.stdout.write(self.style.WARNING(
                            f'{account_code}: Quota hit, retry {attempt + 1}/{MAX_QUOTA_RETRIES} in {wait}s'
                        ))
                        time.sleep(wait)
                        continue

                is_auth = any(kw in error_message.lower() for kw in [
                    'service_account', 'authentication', 'unauthorized', 'forbidden',
                    'invalid credentials', 'access denied', 'no networks to access',
                ])

                return {
                    'account': account_code,
                    'success': False,
                    'error': error_message,
                    'records_created': 0,
                    'is_auth_error': is_auth,
                }

        return {
            'account': account_code,
            'success': False,
            'error': f'Quota exceeded after {MAX_QUOTA_RETRIES} retries',
            'records_created': 0,
            'is_auth_error': False,
        }

    @classmethod
    def handle_cronjob(cls):
        start_time = timezone.now()
        log_file = '/tmp/gam_reports_cron.log'

        try:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file, mode='a'),
                    logging.StreamHandler(),
                ],
            )
            logger.info(f'Starting automated GAM report fetch via cron | {start_time}')

            command = cls()
            command.handle(
                date_from=None, date_to=None, days_back=1,
                parallel=True, max_workers=500,
            )

            duration = (timezone.now() - start_time).total_seconds()
            logger.info(f'Cron completed in {duration:.2f}s')
            cls._cleanup_old_logs()

        except Exception as e:
            duration = (timezone.now() - start_time).total_seconds()
            logger.error(f'Cron failed after {duration:.2f}s: {e}', exc_info=True)
            cls._send_failure_alert(str(e), duration)
            raise

    @classmethod
    def _cleanup_old_logs(cls):
        import glob as glob_mod
        try:
            cutoff = time.time() - (7 * 24 * 60 * 60)
            for f in glob_mod.glob('/tmp/gam_reports_cron*.log'):
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
        except Exception as e:
            logger.warning(f'Log cleanup failed: {e}')

    @classmethod
    def _send_failure_alert(cls, error_message, duration):
        try:
            if hasattr(settings, 'EMAIL_HOST_USER') and settings.EMAIL_HOST_USER:
                send_mail(
                    'GAM Reports Cron Job Failed',
                    f'Error: {error_message}\nDuration: {duration:.2f}s\nTime: {timezone.now()}',
                    settings.EMAIL_HOST_USER,
                    [settings.EMAIL_HOST_USER],
                    fail_silently=True,
                )
        except Exception as e:
            logger.warning(f'Alert send failed: {e}')
