"""
SubPublisherEarningsService — maps GAM MasterMetaData to sub-publishers
via their TrackingAssignment and calculates gross / fee / net.

Attribution: subdomain-only — filters MasterMetaData where
  dimension_type='site' and dimension_value ILIKE subdomain.

Runs after each GAM report sync.
"""

import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from accounts.models import User, TrackingAssignment
from .models import MasterMetaData, SubPublisherEarning

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def _quantize(value, places=6):
    q = Decimal('1').scaleb(-places)
    try:
        return (value if isinstance(value, Decimal) else Decimal(str(value or '0'))).quantize(q, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0').quantize(q, rounding=ROUND_HALF_UP)


class SubPublisherEarningsService:

    @staticmethod
    def calculate_all(date_from=None, date_to=None):
        """
        Calculate earnings for all active sub-publishers within a date range.
        Default: last 7 days if no range specified.
        """
        if not date_from:
            date_to = timezone.now().date()
            date_from = date_to - timedelta(days=7)
        if not date_to:
            date_to = timezone.now().date()

        assignments = (
            TrackingAssignment.objects
            .filter(is_active=True)
            .select_related('sub_publisher', 'partner_admin', 'sub_publisher__parent_publisher')
        )

        total_created = 0
        total_updated = 0

        for ta in assignments:
            try:
                created, updated = SubPublisherEarningsService._calculate_for_assignment(
                    ta, date_from, date_to
                )
                total_created += created
                total_updated += updated
            except Exception as e:
                logger.error(
                    f"Earnings calc failed for sub-publisher {ta.sub_publisher.email}: {e}"
                )

        logger.info(
            f"SubPublisherEarnings: {total_created} created, {total_updated} updated "
            f"({date_from} to {date_to})"
        )
        return {'created': total_created, 'updated': total_updated}

    @staticmethod
    def _calculate_for_assignment(ta, date_from, date_to):
        """Calculate daily earnings for a single tracking assignment (subdomain-only)."""
        sub_pub = ta.sub_publisher
        partner = ta.partner_admin

        parent_publisher = sub_pub.parent_publisher or partner
        if not parent_publisher:
            return 0, 0

        subdomain = (ta.subdomain or '').strip()
        subdomain = subdomain.replace('https://', '').replace('http://', '').rstrip('/')
        if not subdomain:
            return 0, 0

        base_qs = MasterMetaData.objects.filter(
            dimension_type='site',
            date__gte=date_from,
            date__lte=date_to,
            publisher_id=parent_publisher.id,
        ).filter(Q(dimension_value__icontains=subdomain))

        daily_agg = (
            base_qs
            .values('date')
            .annotate(
                total_revenue=Sum('revenue'),
                total_impressions=Sum('impressions'),
                total_clicks=Sum('clicks'),
            )
        )

        fee_pct = sub_pub.custom_fee_percentage or Decimal('0')
        created = 0
        updated = 0

        for day in daily_agg:
            gross = _quantize(day['total_revenue'] or 0)
            imp = day['total_impressions'] or 0
            clicks = day['total_clicks'] or 0
            fee_amount = _quantize(gross * fee_pct / Decimal('100'))
            net = gross - fee_amount
            ecpm = _quantize(gross / imp * 1000, 2) if imp > 0 else Decimal('0')

            obj, was_created = SubPublisherEarning.objects.update_or_create(
                sub_publisher=sub_pub,
                date=day['date'],
                defaults={
                    'partner_admin': partner,
                    'tracking_assignment': ta,
                    'gross_revenue': gross,
                    'fee_percentage': fee_pct,
                    'fee_amount': fee_amount,
                    'net_revenue': net,
                    'impressions': imp,
                    'clicks': clicks,
                    'ecpm': ecpm,
                    'source_dimension_type': 'site',
                    'source_dimension_value': subdomain,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return created, updated

    @staticmethod
    def calculate_for_sub_publisher(sub_publisher_id, date_from=None, date_to=None):
        """Calculate earnings for a single sub-publisher."""
        try:
            ta = TrackingAssignment.objects.select_related(
                'sub_publisher', 'partner_admin'
            ).get(sub_publisher_id=sub_publisher_id, is_active=True)
        except TrackingAssignment.DoesNotExist:
            return {'created': 0, 'updated': 0, 'error': 'No active tracking assignment.'}

        if not date_from:
            date_to = timezone.now().date()
            date_from = date_to - timedelta(days=30)
        if not date_to:
            date_to = timezone.now().date()

        created, updated = SubPublisherEarningsService._calculate_for_assignment(
            ta, date_from, date_to
        )
        return {'created': created, 'updated': updated}
