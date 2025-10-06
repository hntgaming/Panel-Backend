"""
Management command to create parent user accounts for GAM networks
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import User, PartnerPermission
from gam_accounts.models import GAMNetwork
import re


class Command(BaseCommand):
    help = 'Create parent user accounts for all parent GAM networks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get all parent networks
        parent_networks = GAMNetwork.objects.filter(network_type='parent')
        
        if not parent_networks.exists():
            self.stdout.write(self.style.ERROR('No parent networks found'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nFound {parent_networks.count()} parent network(s)'))
        self.stdout.write('=' * 80)
        
        created_count = 0
        skipped_count = 0
        
        for network in parent_networks:
            # Extract first word from network name
            first_name = network.network_name.split()[0].lower()
            # Remove special characters
            first_name = re.sub(r'[^a-z0-9]', '', first_name)
            
            email = f"{first_name}@hntgaming.me"
            password = "ParentPass123!"  # Default password for all parent users
            
            self.stdout.write(f'\n📝 Network: {network.network_name}')
            self.stdout.write(f'   Code: {network.network_code}')
            self.stdout.write(f'   Email: {email}')
            
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.WARNING(f'   ⚠️  User already exists - skipping'))
                skipped_count += 1
                continue
            
            if dry_run:
                self.stdout.write(self.style.SUCCESS(f'   ✅ Would create user (dry run)'))
                created_count += 1
                continue
            
            try:
                with transaction.atomic():
                    # Create parent user (email is username for this model)
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=password,
                    )
                    # Set additional fields
                    user.role = 'parent'
                    user.status = 'active'
                    user.company_name = network.network_name
                    user.save()
                    
                    # Link user to parent network
                    # Store parent network ID in a custom field or use PartnerPermission
                    perm = PartnerPermission.objects.create(
                        user=user,
                        permission='access_reports',  # Base permission
                        parent_gam_network=network
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f'   ✅ Created user successfully'))
                    self.stdout.write(f'      Password: {password}')
                    created_count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ❌ Error: {str(e)}'))
        
        self.stdout.write('\n' + '=' * 80)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'\n✅ DRY RUN Summary:'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Summary:'))
        self.stdout.write(f'   Created: {created_count}')
        self.stdout.write(f'   Skipped: {skipped_count}')
        self.stdout.write(f'   Total: {created_count + skipped_count}')
        
        if not dry_run and created_count > 0:
            self.stdout.write('\n' + self.style.WARNING('⚠️  Default password for all parent users: ParentPass123!'))
            self.stdout.write(self.style.WARNING('   Please ask parent users to change their password after first login'))

