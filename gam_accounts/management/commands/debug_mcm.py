# gam_accounts/management/commands/debug_mcm.py - Enhanced API-first testing

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from gam_accounts.services import MCMService
from gam_accounts.models import MCMInvitation, GAMNetwork
import json
from datetime import datetime

User = get_user_model()

class Command(BaseCommand):
    help = 'Enhanced debug MCM invitation process with API-first approach'

    def add_arguments(self, parser):
        # Basic parameters
        parser.add_argument('--parent', default='152344380', help='Parent network code')
        parser.add_argument('--child', default='22878573653', help='Child network code')
        parser.add_argument('--name', default='Helal Ahmed (DP News)', help='Child network name')
        parser.add_argument('--email', default='admin@hntgaming.me', help='Primary contact email')
        
        # NEW: Enhanced parameters for your business requirements
        parser.add_argument(
            '--delegation-type', 
            choices=['MANAGE_INVENTORY', 'MANAGE_ACCOUNT'],
            default='MANAGE_ACCOUNT',
            help='MCM delegation type'
        )
        parser.add_argument(
            '--revenue-share', 
            type=int, 
            default=20,
            help='Revenue share percentage for parent (0-100)'
        )
        parser.add_argument(
            '--force-manual', 
            action='store_true',
            help='Skip API and use manual workflow only'
        )
        
        # Debug options
        parser.add_argument('--list-invitations', action='store_true', help='List existing invitations')
        parser.add_argument('--cleanup', action='store_true', help='Clean up test invitations')
        parser.add_argument('--verbose', action='store_true', help='Show detailed output')

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        self.stdout.write(self.style.HTTP_INFO("🔍 ENHANCED MCM INVITATION DEBUG TOOL"))
        self.stdout.write(self.style.HTTP_INFO("=" * 60))
        
        # Handle special actions first
        if options['list_invitations']:
            self.list_invitations()
            return
        
        if options['cleanup']:
            self.cleanup_test_invitations()
            return
        
        # Show current parameters
        self.show_parameters(options)
        
        # Run the invitation test
        self.run_invitation_test(options)
    
    def show_parameters(self, options):
        """Display current test parameters"""
        self.stdout.write("\n📋 Test Parameters:")
        self.stdout.write(f"  Parent Network: {options['parent']}")
        self.stdout.write(f"  Child Network:  {options['child']} ({options['name']})")
        self.stdout.write(f"  Contact Email:  {options['email']}")
        self.stdout.write(f"  Delegation:     {options['delegation_type']}")
        
        if options['delegation_type'] == 'MANAGE_ACCOUNT':
            self.stdout.write(f"  Revenue Split:  Parent {options['revenue_share']}% | Child {100 - options['revenue_share']}%")
        
        self.stdout.write(f"  Force Manual:   {'Yes' if options['force_manual'] else 'No (API first)'}")
        self.stdout.write("-" * 50)
    
    def run_invitation_test(self, options):
        """Run the main invitation test"""
        try:
            # Get or create test user
            test_user, created = User.objects.get_or_create(
                username='mcm_debug_user',
                defaults={
                    'email': 'debug@mcm.test',
                    'first_name': 'MCM',
                    'last_name': 'Debug'
                }
            )
            
            if created:
                self.stdout.write(f"📝 Created debug user: {test_user.username}")
            
            # Check for existing invitations
            existing = MCMInvitation.objects.filter(
                parent_network__network_code=options['parent'],
                child_network_code=options['child']
            ).first()
            
            if existing:
                self.stdout.write(f"⚠️  Found existing invitation: {existing.invitation_id} (Status: {existing.status})")
                if existing.status == 'pending':
                    self.stdout.write("   Continuing with existing invitation...")
                    self.show_invitation_details(existing)
                    return
            
            # Prepare invitation parameters
            invitation_params = {
                'parent_network_code': options['parent'],
                'child_network_code': options['child'],
                'child_network_name': options['name'],
                'primary_contact_email': options['email'],
                'delegation_type': options['delegation_type'],
                'force_manual': options['force_manual'],
                'invited_by': test_user
            }
            
            # Add revenue share for MANAGE_ACCOUNT
            if options['delegation_type'] == 'MANAGE_ACCOUNT':
                invitation_params['revenue_share_percentage'] = options['revenue_share']
            
            self.stdout.write(f"\n🚀 Starting {'Manual' if options['force_manual'] else 'API-first'} invitation process...")
            
            # Call the enhanced MCM service
            result = MCMService.send_invitation(**invitation_params)
            
            # Display results
            self.display_results(result, options)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Fatal error: {str(e)}"))
            if options['verbose']:
                import traceback
                self.stdout.write(traceback.format_exc())
    
    def display_results(self, result, options):
        """Display detailed results"""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("📊 INVITATION RESULTS")
        self.stdout.write("=" * 50)
        
        if result.get('success'):
            # Success case
            self.stdout.write(self.style.SUCCESS("✅ SUCCESS!"))
            
            invitation = result.get('invitation')
            if invitation:
                self.show_invitation_details(invitation)
                
                # Show specific success type
                if result.get('real_invitation_sent'):
                    self.stdout.write(self.style.SUCCESS("🎉 REAL GAM API INVITATION SENT!"))
                    if result.get('gam_company_id'):
                        self.stdout.write(f"   GAM Company ID: {result['gam_company_id']}")
                    self.stdout.write(f"   Method: {invitation.api_method_used or 'API'}")
                    self.stdout.write(f"   Email sent to: {invitation.primary_contact_email}")
                    self.stdout.write("\n🎯 Next Steps for Child Publisher:")
                    self.stdout.write("   1. Check email at: " + invitation.primary_contact_email)
                    self.stdout.write("   2. Log into GAM account: " + invitation.child_network_code)
                    self.stdout.write("   3. Go to Admin > MCM > Invitations")
                    self.stdout.write("   4. Accept the invitation")
                    self.stdout.write("   5. Revenue split will be automatic!")
                else:
                    self.stdout.write(self.style.WARNING("📝 Manual workflow required"))
                    self.stdout.write("   API attempt failed, manual steps provided")
                    if result.get('manual_steps'):
                        self.stdout.write("\n📋 Manual Steps:")
                        for i, step in enumerate(result['manual_steps'], 1):
                            self.stdout.write(f"   {i}. {step}")
        else:
            # Failure case
            self.stdout.write(self.style.ERROR("❌ FAILED"))
            self.stdout.write(f"Error: {result.get('error', 'Unknown error')}")
            
            # Show troubleshooting if available
            if result.get('troubleshooting'):
                troubleshooting = result['troubleshooting']
                self.stdout.write("\n💡 Troubleshooting:")
                
                if troubleshooting.get('possible_causes'):
                    self.stdout.write("  Possible causes:")
                    for cause in troubleshooting['possible_causes']:
                        self.stdout.write(f"    - {cause}")
                
                if troubleshooting.get('next_steps'):
                    self.stdout.write("  Suggested next steps:")
                    for step in troubleshooting['next_steps']:
                        self.stdout.write(f"    - {step}")
        
        # Show debug info if verbose
        if options.get('verbose') and result.get('debug_info'):
            self.stdout.write("\n🔧 Debug Information:")
            debug_info = result['debug_info']
            for key, value in debug_info.items():
                if key != 'errors':
                    status_icon = "✅" if "SUCCESS" in str(value) else "❌" if "ERROR" in str(value) else "ℹ️"
                    self.stdout.write(f"  {status_icon} {key}: {value}")
            
            if debug_info.get('errors'):
                self.stdout.write("  🚨 Errors:")
                for error in debug_info['errors']:
                    self.stdout.write(f"    - {error}")
        
        # Show raw JSON for technical analysis
        if options.get('verbose'):
            self.stdout.write("\n📄 Raw JSON Response:")
            self.stdout.write(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    
    def show_invitation_details(self, invitation):
        """Show detailed invitation information"""
        self.stdout.write(f"\n📧 Invitation Details:")
        self.stdout.write(f"   ID: {invitation.invitation_id}")
        self.stdout.write(f"   Status: {invitation.status}")
        self.stdout.write(f"   Delegation: {invitation.delegation_type}")
        
        if invitation.revenue_share_percentage:
            self.stdout.write(f"   Revenue Split: Parent {invitation.revenue_share_percentage}% | Child {invitation.child_revenue_percentage}%")
        
        self.stdout.write(f"   Real API Sent: {'Yes' if invitation.real_invitation_sent else 'No'}")
        self.stdout.write(f"   Created: {invitation.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if invitation.expires_at:
            self.stdout.write(f"   Expires: {invitation.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if invitation.days_until_expiry is not None:
                self.stdout.write(f"   Days Left: {invitation.days_until_expiry}")
    
    def list_invitations(self):
        """List all existing MCM invitations"""
        self.stdout.write("📋 Existing MCM Invitations:")
        self.stdout.write("=" * 70)
        
        invitations = MCMInvitation.objects.select_related('parent_network').order_by('-created_at')
        
        if not invitations:
            self.stdout.write("   No invitations found")
            return
        
        for inv in invitations:
            method = "API" if inv.real_invitation_sent else "Manual"
            revenue = f" ({inv.revenue_share_percentage}%)" if inv.revenue_share_percentage else ""
            
            self.stdout.write(f"   {inv.invitation_id}")
            self.stdout.write(f"     → {inv.parent_network.network_code} → {inv.child_network_code}")
            self.stdout.write(f"     → Status: {inv.status} | Method: {method} | Type: {inv.delegation_type}{revenue}")
            self.stdout.write(f"     → Created: {inv.created_at.strftime('%Y-%m-%d %H:%M')}")
            
            if inv.gam_company_id:
                self.stdout.write(f"     → GAM Company ID: {inv.gam_company_id}")
            
            self.stdout.write("")
    
    def cleanup_test_invitations(self):
        """Clean up test invitations"""
        self.stdout.write("🧹 Cleaning up test invitations...")
        
        # Find test invitations (those created by debug user or with test patterns)
        test_invitations = MCMInvitation.objects.filter(
            invitation_id__icontains='debug'
        ) | MCMInvitation.objects.filter(
            invited_by__username='mcm_debug_user'
        ) | MCMInvitation.objects.filter(
            child_network_code__in=['22878573653', 'test_network']
        )
        
        count = test_invitations.count()
        
        if count == 0:
            self.stdout.write("   No test invitations found")
            return
        
        self.stdout.write(f"   Found {count} test invitation(s)")
        
        # Ask for confirmation in interactive mode
        if not hasattr(self, '_called_from_command_line'):
            confirm = input("   Delete these invitations? (y/N): ")
            if confirm.lower() != 'y':
                self.stdout.write("   Cleanup cancelled")
                return
        
        # Delete the invitations
        deleted_count, _ = test_invitations.delete()
        self.stdout.write(self.style.SUCCESS(f"   ✅ Deleted {deleted_count} test invitations"))
        
        # Also clean up debug user if no other data
        try:
            debug_user = User.objects.get(username='mcm_debug_user')
            if not debug_user.mcminvitation_set.exists():
                debug_user.delete()
                self.stdout.write("   ✅ Deleted debug user")
        except User.DoesNotExist:
            pass
    
    def add_arguments_help(self):
        """Show detailed help for command arguments"""
        help_text = """
🔍 Enhanced MCM Debug Command Help

BASIC USAGE:
  python manage.py debug_mcm                     # Test with default settings
  python manage.py debug_mcm --verbose           # Show detailed debug info

BUSINESS SCENARIO (Your Boss's Requirements):
  python manage.py debug_mcm \
    --parent 152344380 \
    --child 22878573653 \
    --name "Helal Ahmed (DP News)" \
    --email admin@hntgaming.me \
    --delegation-type MANAGE_ACCOUNT \
    --revenue-share 20

TESTING SCENARIOS:
  python manage.py debug_mcm --force-manual      # Test manual workflow only
  python manage.py debug_mcm --delegation-type MANAGE_INVENTORY  # Test inventory management
  python manage.py debug_mcm --revenue-share 30  # Test different revenue split

UTILITY COMMANDS:
  python manage.py debug_mcm --list-invitations  # Show all invitations
  python manage.py debug_mcm --cleanup           # Clean up test data

PARAMETERS:
  --parent          Parent network code (default: 152344380)
  --child           Child network code (default: 22878573653)
  --name            Child network display name
  --email           Primary contact email for invitation
  --delegation-type MANAGE_INVENTORY or MANAGE_ACCOUNT
  --revenue-share   Parent's percentage (0-100, required for MANAGE_ACCOUNT)
  --force-manual    Skip API, use manual workflow only
  --verbose         Show detailed debug information
        """
        return help_text