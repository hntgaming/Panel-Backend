
"""
Core models - Base model classes used across the platform
"""
from django.db import models

class TimeStampedModel(models.Model):
    """
    Abstract base model that provides self-updating 'created' and 'modified' fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class StatusChoices(models.TextChoices):
    """
    Common status choices used across different models
    """
    ACTIVE = 'active', 'Active'
    INACTIVE = 'inactive', 'Inactive'
    PENDING = 'pending', 'Pending'
    PENDING_APPROVAL = 'pending_approval', 'Pending Approval'
    SUSPENDED = 'suspended', 'Suspended'
