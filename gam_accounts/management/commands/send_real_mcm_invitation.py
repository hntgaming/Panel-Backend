# gam_accounts/management/commands/send_real_mcm_invitation.py

from django.core.management.base import BaseCommand
from django.conf import settings
from gam_accounts import gam_config
from gam_accounts.services import GAMNetworkService, MCMService

class Command(BaseCommand):
    help = 'Send REAL MCM invitation via GAM API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--child-network',
            type=str,
            help='Child network code (defaults to GAM_CHILD_NETWORK_CODE from settings)',
            default=None
        )
        parser.add_argument(
            '--child-name',
            type=str,
            help='Child network display name',
            default=''
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("🚀 Sending REAL GAM MCM Invitation..."))
        
        # Step 1: Sync parent network first
        self.stdout.write("📡 Syncing parent network...")
        sync_result = GAMNetworkService.sync_parent_network()
        
        if not sync_result['success']:
            self.stdout.write(
                self.style.ERROR(f"❌ Failed to sync parent network: {sync_result['error']}")
            )
            return
        
        parent_network = sync_result['network']
        self.stdout.write(
            self.style.SUCCESS(f"✅ Parent network synced: {parent_network.network_name} ({parent_network.network_code})")
        )
        
        # Step 2: Get real child network name if not provided
        child_network_code = options['child_network'] or settings.GAM_CHILD_NETWORK_CODE
        child_network_name = options['child_name']
        
        if not child_network_name:
            self.stdout.write(f"🔍 Fetching real name for network {child_network_code}...")
            try:
                network_service = gam_config.get_service('NetworkService', network_code=child_network_code)
                network_info = network_service.getCurrentNetwork()
                if hasattr(network_info, 'displayName'):
                    child_network_name = network_info.displayName
                    self.stdout.write(f"✅ Found real name: {child_network_name}")
                else:
                    child_network_name = f"Network {child_network_code}"
                    self.stdout.write(f"⚠️  Couldn't get real name, using: {child_network_name}")
            except Exception as e:
                child_network_name = f"Network {child_network_code}"
                self.stdout.write(f"⚠️  Error getting real name: {str(e)}")
                self.stdout.write(f"    Using fallback: {child_network_name}")
        
        # Step 3: Send REAL MCM invitation via GAM API
        
        self.stdout.write(f"📤 Sending REAL GAM MCM invitation...")
        self.stdout.write(f"   From: {parent_network.network_name} ({parent_network.network_code})")
        self.stdout.write(f"   To: {child_network_name} ({child_network_code})")
        self.stdout.write(f"   🔥 This will make a REAL GAM API call!")
        
        invitation_result = MCMService.send_invitation(
            parent_network_code=parent_network.network_code,
            child_network_code=child_network_code,
            child_network_name=child_network_name
        )
        
        if invitation_result['success']:
            invitation = invitation_result['invitation']
            self.stdout.write(
                self.style.SUCCESS("🎉 REAL GAM MCM Invitation sent successfully!")
            )
            self.stdout.write(f"   ✅ Invitation ID: {invitation.invitation_id}")
            self.stdout.write(f"   ✅ Status: {invitation.status}")
            self.stdout.write(f"   ✅ Expires: {invitation.expires_at}")
            
            if 'invitation_url' in invitation_result and invitation_result['invitation_url']:
                self.stdout.write(f"   🔗 Invitation URL: {invitation_result['invitation_url']}")
            
            self.stdout.write(
                self.style.WARNING(
                    f"\n📧 The child network ({child_network_code}) should now receive "
                    f"the invitation in their GAM account!"
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    f"\n🎯 Tell your boss to check the GAM account for network {child_network_code} "
                    f"for the MCM invitation!"
                )
            )
            
        else:
            self.stdout.write(
                self.style.ERROR(f"❌ Failed to send REAL GAM MCM invitation: {invitation_result['error']}")
            )
            
            # Show specific error guidance
            error = invitation_result['error'].lower()
            if 'permission' in error:
                self.stdout.write(
                    self.style.WARNING(
                        "💡 Your service account may need MCM permissions. "
                        "Ask your GAM admin to grant Multiple Customer Management access."
                    )
                )
            elif 'network_not_found' in error:
                self.stdout.write(
                    self.style.WARNING(
                        f"💡 Child network {child_network_code} may not exist or be accessible."
                    )
                )
            elif 'already_invited' in error:
                self.stdout.write(
                    self.style.WARNING(
                        "💡 Check if there's already a pending invitation for this network."
                    )
                )
            elif 'service' in error:
                self.stdout.write(
                    self.style.WARNING(
                        "💡 MultipleCustomerManagementService may not be available. "
                        "Check API version and permissions."
                    )
                )