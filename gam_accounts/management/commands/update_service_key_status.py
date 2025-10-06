# gam_accounts/management/commands/update_service_key_status.py

from django.core.management.base import BaseCommand
from django.db import transaction
from gam_accounts.models import MCMInvitation
from gam_accounts.services import GAMNetworkService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Manually update service key status for all accounts by testing GAM API access'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-active',
            action='store_true',
            help='Force all accounts to active without testing GAM API access',
        )
        parser.add_argument(
            '--test-access',
            action='store_true',
            help='Test GAM API access for each account and update status accordingly',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Starting service key status update...'))
        
        # Get all accounts (including inactive ones for force-active mode)
        if options['force_active']:
            accounts = MCMInvitation.objects.all()
        else:
            accounts = MCMInvitation.objects.filter(user_status='active')
        total_accounts = accounts.count()
        
        self.stdout.write(f'📊 Found {total_accounts} accounts to process')
        
        if options['force_active']:
            self.stdout.write(self.style.WARNING('⚠️ Force active mode: Setting all accounts to active without testing'))
            self._force_all_active(accounts)
        elif options['test_access']:
            self.stdout.write('🔍 Testing GAM API access for each account...')
            self._test_and_update_status(accounts)
        else:
            # Default: Set all to active (as requested by user)
            self.stdout.write('✅ Setting all active accounts to service key active')
            self._set_all_active(accounts)

    def _force_all_active(self, accounts):
        """Force all accounts to active status"""
        updated_count = 0
        
        with transaction.atomic():
            for account in accounts:
                if not account.service_account_enabled:
                    account.service_account_enabled = True
                    account.save()
                    updated_count += 1
                    self.stdout.write(f'  ✅ {account.child_network_code}: Set to active')
                else:
                    self.stdout.write(f'  ⏭️  {account.child_network_code}: Already active')
        
        self.stdout.write(self.style.SUCCESS(f'🎉 Updated {updated_count} accounts to active status'))

    def _set_all_active(self, accounts):
        """Set all accounts to active status (default behavior)"""
        updated_count = 0
        
        with transaction.atomic():
            for account in accounts:
                if not account.service_account_enabled:
                    account.service_account_enabled = True
                    account.save()
                    updated_count += 1
                    self.stdout.write(f'  ✅ {account.child_network_code}: Set to active')
                else:
                    self.stdout.write(f'  ⏭️  {account.child_network_code}: Already active')
        
        self.stdout.write(self.style.SUCCESS(f'🎉 Updated {updated_count} accounts to active status'))

    def _test_and_update_status(self, accounts):
        """Test GAM API access for each account and update status accordingly"""
        active_count = 0
        inactive_count = 0
        
        with transaction.atomic():
            for account in accounts:
                try:
                    # Test GAM API access
                    client = GAMNetworkService.get_googleads_client(account.child_network_code)
                    
                    # Test with a simple API call
                    network_service = client.GetService("NetworkService", version="v202508")
                    network = network_service.getCurrentNetwork()
                    
                    # If we get here, GAM API is accessible
                    if not account.service_account_enabled:
                        account.service_account_enabled = True
                        account.save()
                        active_count += 1
                        self.stdout.write(f'  ✅ {account.child_network_code}: GAM accessible, set to active')
                    else:
                        self.stdout.write(f'  ✅ {account.child_network_code}: GAM accessible, already active')
                        
                except Exception as e:
                    # GAM API access failed
                    if account.service_account_enabled:
                        account.service_account_enabled = False
                        account.save()
                        inactive_count += 1
                        self.stdout.write(f'  ❌ {account.child_network_code}: GAM not accessible, set to inactive ({str(e)[:50]}...)')
                    else:
                        self.stdout.write(f'  ❌ {account.child_network_code}: GAM not accessible, already inactive ({str(e)[:50]}...)')
        
        self.stdout.write(self.style.SUCCESS(f'🎉 Testing complete: {active_count} active, {inactive_count} inactive'))
