# gam_accounts/management/commands/cleanup_mock_invitations.py

from django.core.management.base import BaseCommand
from gam_accounts.models import MCMInvitation

class Command(BaseCommand):
    help = 'Clean up mock MCM invitations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--child-network',
            type=str,
            help='Child network code to clean up',
            default=None
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clean up all mock invitations'
        )

    def handle(self, *args, **options):
        self.stdout.write("🧹 Cleaning up mock MCM invitations...")
        
        if options['all']:
            # Delete all mock invitations (those starting with 'mcm_')
            mock_invitations = MCMInvitation.objects.filter(invitation_id__startswith='mcm_')
            count = mock_invitations.count()
            mock_invitations.delete()
            self.stdout.write(
                self.style.SUCCESS(f"✅ Deleted {count} mock invitations")
            )
        elif options['child_network']:
            # Delete invitations for specific child network
            child_network = options['child_network']
            invitations = MCMInvitation.objects.filter(child_network_code=child_network)
            count = invitations.count()
            
            if count > 0:
                self.stdout.write(f"Found {count} invitations for network {child_network}:")
                for inv in invitations:
                    self.stdout.write(f"  - ID: {inv.invitation_id}, Status: {inv.status}")
                
                invitations.delete()
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Deleted {count} invitations for network {child_network}")
                )
            else:
                self.stdout.write(f"No invitations found for network {child_network}")
        else:
            # Show all invitations
            all_invitations = MCMInvitation.objects.all()
            self.stdout.write(f"Found {all_invitations.count()} total invitations:")
            
            for inv in all_invitations:
                invitation_type = "Mock" if inv.invitation_id.startswith('mcm_') else "Real"
                self.stdout.write(f"  - {invitation_type}: {inv.child_network_code} ({inv.status})")
            
            self.stdout.write("\nUse --all to delete all mock invitations")
            self.stdout.write("Use --child-network=CODE to delete specific network invitations")