# gam_accounts/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import MCMInvitation
from reports.services import GAMReportService
import logging

logger = logging.getLogger(__name__)

# Sub-reports functionality removed - no longer needed for managed inventory publisher dashboard

@receiver(post_save, sender=MCMInvitation)
def log_status_change(sender, instance, created, **kwargs):
    """
    Log when status changes to invited/approved to enable main reports
    """
    if not created and instance.status in ['invited', 'approved'] and instance.user_status == 'active':
        logger.info(f"🎉 Account {instance.child_network_code} status changed to {instance.status}")
        logger.info("✅ Account is now eligible for main report fetching")
