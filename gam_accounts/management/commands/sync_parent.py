from django.core.management.base import BaseCommand
from gam_accounts.services import GAMNetworkService

class Command(BaseCommand):
    help = 'Sync parent GAM network'
    
    def handle(self, *args, **options):
        self.stdout.write('Syncing parent network...')
        
        result = GAMNetworkService.sync_parent_network()
        
        if result['success']:
            network = result['network']
            action = "Created" if result['created'] else "Updated"
            
            self.stdout.write(self.style.SUCCESS(f'✅ {action} parent network:'))
            self.stdout.write(f"  Name: {network.network_name}")
            self.stdout.write(f"  Code: {network.network_code}")
            self.stdout.write(f"  Type: {network.network_type}")
            self.stdout.write(f"  Status: {network.status}")
            self.stdout.write(f"  Currency: {network.currency_code}")
            self.stdout.write(f"  Time Zone: {network.time_zone}")
        else:
            self.stdout.write(self.style.ERROR(f'❌ Failed to sync: {result["error"]}'))