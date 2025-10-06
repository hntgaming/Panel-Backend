from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from gam_accounts.models import MCMInvitation, AssignedPartnerChildAccount
from .models import MasterMetaData
@receiver(post_save, sender=AssignedPartnerChildAccount)
def update_partner_assignments(sender, instance, created, **kwargs):
    """
    Update partner_id in MasterMetaData when partner assignments change
    """
    if created:
        MasterMetaData.objects.filter(
            invitation=instance.invitation
        ).update(partner_id=instance.partner.id)
@receiver(post_delete, sender=AssignedPartnerChildAccount)
def clear_partner_assignments(sender, instance, **kwargs):
    """
    Clear partner_id in MasterMetaData when assignment is deleted
    """
    MasterMetaData.objects.filter(
        invitation=instance.invitation
    ).update(partner_id=None)
@receiver(post_save, sender=MCMInvitation)
def handle_invitation_status_change(sender, instance, **kwargs):
    """
    Handle status changes in MCM invitations
    """
    import logging
    logger = logging.getLogger(__name__)
    if instance.user_status == 'inactive':
        record_count = MasterMetaData.objects.filter(invitation=instance).count()
        logger.info(f"📊 MCM invitation {instance.id} marked inactive - {record_count} report records affected")