"""
Remove network-related models and fields:
- User.network_id
- ParentNetwork model
- PublisherAccountAccess model
- PermissionAuditLog.child_network_code, parent_network_code
- Simplify PermissionAuditLog.ACTION_CHOICES
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_gam_credential_subdomain_only'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='network_id',
        ),
        migrations.RemoveField(
            model_name='permissionauditlog',
            name='child_network_code',
        ),
        migrations.RemoveField(
            model_name='permissionauditlog',
            name='parent_network_code',
        ),
        migrations.DeleteModel(
            name='PublisherAccountAccess',
        ),
        migrations.DeleteModel(
            name='ParentNetwork',
        ),
    ]
