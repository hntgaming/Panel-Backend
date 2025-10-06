"""
Signal handlers for accounts app
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import PartnerPermission
from .permissions import clear_permission_cache
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=PartnerPermission)
def clear_cache_on_permission_save(sender, instance, **kwargs):
    """Clear permission cache when permission is created or updated"""
    clear_permission_cache(instance.user_id)
    logger.info(f"Cleared permission cache for user {instance.user_id} after save")


@receiver(post_delete, sender=PartnerPermission)
def clear_cache_on_permission_delete(sender, instance, **kwargs):
    """Clear permission cache when permission is deleted"""
    clear_permission_cache(instance.user_id)
    logger.info(f"Cleared permission cache for user {instance.user_id} after delete")

