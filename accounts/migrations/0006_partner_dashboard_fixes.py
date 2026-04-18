from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_add_gam_type_to_user'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='trackingassignment',
            constraint=models.CheckConstraint(
                check=models.Q(tracking_type__in=['utm', 'subdomain']),
                name='valid_tracking_type',
            ),
        ),
        migrations.AlterField(
            model_name='publisheraccountaccess',
            name='publisher',
            field=models.ForeignKey(
                blank=True,
                help_text='Publisher user',
                limit_choices_to={'role': 'publisher'},
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name='assigned_accounts',
                to='accounts.user',
            ),
        ),
        migrations.AlterField(
            model_name='parentnetwork',
            name='user',
            field=models.OneToOneField(
                blank=True,
                help_text='Partner-Admin user',
                limit_choices_to={'role': 'partner_admin'},
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name='parent_network_assignment',
                to='accounts.user',
            ),
        ),
    ]
