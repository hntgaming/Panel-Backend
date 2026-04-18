"""
Simplify MasterMetaData network fields:
- Remove parent_network_code
- Rename child_network_code -> network_code
- Update unique_together and indexes
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0008_remove_tracking_models'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mastermetadata',
            name='parent_network_code',
        ),
        migrations.RenameField(
            model_name='mastermetadata',
            old_name='child_network_code',
            new_name='network_code',
        ),
        migrations.AlterField(
            model_name='mastermetadata',
            name='network_code',
            field=models.CharField(
                db_index=True,
                help_text="Partner's GAM network code (from GAMCredential)",
                max_length=100,
            ),
        ),
        migrations.AlterUniqueTogether(
            name='mastermetadata',
            unique_together={('network_code', 'date', 'dimension_type', 'dimension_value')},
        ),
    ]
