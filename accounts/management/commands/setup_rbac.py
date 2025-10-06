"""
Management command to set up RBAC system
Creates permissions, role defaults, and seeds the system
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import Permission, RolePermission


class Command(BaseCommand):
    help = 'Set up RBAC system with permissions and role defaults'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset existing permissions and role defaults',
        )
    
    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Resetting RBAC system...')
            Permission.objects.all().delete()
            RolePermission.objects.all().delete()
        
        with transaction.atomic():
            self.create_permissions()
            self.create_role_defaults()
        
        self.stdout.write(
            self.style.SUCCESS('Successfully set up RBAC system')
        )
    
    def create_permissions(self):
        """Create all permissions"""
        self.stdout.write('Creating permissions...')
        
        permissions_data = [
            # Admin-only permissions
            ('manage_partners', 'Manage Partners page', 'admin'),
            ('settings', 'Settings page', 'admin'),
            
            # Parent/Partner configurable permissions
            ('managed_sites', 'Managed Sites', 'management'),
            ('mcm_invites', 'MCM Invites', 'management'),
            ('verification', 'Verification', 'management'),
            ('reports', 'Reports', 'operations'),
            ('smart_alerts', 'Smart Alerts', 'operations'),
            ('ticket_board', 'Ticket Board', 'operations'),
        ]
        
        created_count = 0
        for key, description, category in permissions_data:
            permission, created = Permission.objects.get_or_create(
                key=key,
                defaults={
                    'description': description,
                    'category': category
                }
            )
            if created:
                created_count += 1
                self.stdout.write(f'  Created permission: {key}')
            else:
                self.stdout.write(f'  Permission already exists: {key}')
        
        self.stdout.write(f'Created {created_count} new permissions')
    
    def create_role_defaults(self):
        """Create role permission defaults"""
        self.stdout.write('Creating role permission defaults...')
        
        # Get all permissions
        all_permissions = Permission.objects.all()
        
        # Admin gets all permissions
        admin_permissions = all_permissions
        
        # Parent gets all permissions except admin-only ones
        parent_permissions = all_permissions.exclude(
            key__in=['settings', 'manage_partners']
        )
        
        # Partner gets no default permissions (all configurable)
        partner_permissions = Permission.objects.none()
        
        # Create role permissions
        role_permissions_data = [
            ('ADMIN', admin_permissions),
            ('PARENT', parent_permissions),
            ('PARTNER', partner_permissions),
        ]
        
        created_count = 0
        for role, permissions in role_permissions_data:
            for permission in permissions:
                role_permission, created = RolePermission.objects.get_or_create(
                    role=role,
                    permission=permission
                )
                if created:
                    created_count += 1
                    self.stdout.write(f'  Created {role} -> {permission.key}')
                else:
                    self.stdout.write(f'  {role} -> {permission.key} already exists')
        
        self.stdout.write(f'Created {created_count} new role permission defaults')
        
        # Print summary
        self.stdout.write('\nRole Permission Summary:')
        for role in ['ADMIN', 'PARENT', 'PARTNER']:
            count = RolePermission.objects.filter(role=role).count()
            self.stdout.write(f'  {role}: {count} permissions')
