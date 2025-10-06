# gam_accounts/management/commands/get_network_info.py

from django.core.management.base import BaseCommand
from gam_accounts.gam_config import gam_config

class Command(BaseCommand):
    help = 'Get real network information from GAM API'

    def add_arguments(self, parser):
        parser.add_argument(
            'network_code',
            type=str,
            help='Network code to get information for'
        )

    def handle(self, *args, **options):
        network_code = options['network_code']
        
        self.stdout.write(f"🔍 Getting network information for: {network_code}")
        
        try:
            # Get network service for the specific network
            network_service = gam_config.get_service('NetworkService', network_code=network_code)
            
            # Get current network information
            network_info = network_service.getCurrentNetwork()
            
            self.stdout.write(
                self.style.SUCCESS("✅ Network information retrieved!")
            )
            
            # Display network details
            if hasattr(network_info, 'displayName'):
                self.stdout.write(f"   📛 Network Name: {network_info.displayName}")
                self.stdout.write(f"   🏷️  Network Code: {network_info.networkCode}")
                self.stdout.write(f"   💰 Currency: {getattr(network_info, 'currencyCode', 'Unknown')}")
                self.stdout.write(f"   🌍 Time Zone: {getattr(network_info, 'timeZone', 'Unknown')}")
                
                # Return the real name for use
                real_name = network_info.displayName
                self.stdout.write(
                    self.style.WARNING(f"\n🎯 Use this real name: {real_name}")
                )
                
            else:
                self.stdout.write(f"Raw response: {network_info}")
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Failed to get network info: {str(e)}")
            )
            
            # Handle specific errors
            error_str = str(e).lower()
            if 'permission' in error_str or 'access' in error_str:
                self.stdout.write(
                    self.style.WARNING("💡 Your service account may not have access to this network")
                )
            elif 'not found' in error_str:
                self.stdout.write(
                    self.style.WARNING(f"💡 Network {network_code} may not exist")
                )