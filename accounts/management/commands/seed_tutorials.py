from django.core.management.base import BaseCommand
from accounts.models import Tutorial


SEED_DATA = [
    {
        'title': 'Getting Started with the Publisher Dashboard',
        'slug': 'getting-started',
        'category': 'getting_started',
        'order': 1,
        'summary': 'Learn how to navigate the dashboard and understand your reporting data.',
        'target_roles': [],
        'content': """# Getting Started

Welcome to the Publisher Dashboard. This guide will help you understand the key sections.

## Dashboard Overview

Your dashboard shows a summary of your advertising performance including:

- **Impressions** — how many times ads were displayed on your traffic
- **Revenue** — gross earnings from ad impressions
- **eCPM** — effective cost per thousand impressions
- **CTR** — click-through rate

## Navigation

Use the sidebar to access different sections:

- **Dashboard** — at-a-glance performance summary
- **Reports** — detailed breakdowns by date, device, country, and more
- **Earnings** — monthly earnings with fee breakdown
- **Tutorials** — this help center

## Understanding Your Data

All reporting data is sourced directly from Google Ad Manager. Data is synced automatically and typically reflects a 24-48 hour delay from GAM's reporting pipeline.
""",
    },
    {
        'title': 'How UTM Tracking Works',
        'slug': 'utm-tracking',
        'category': 'tracking',
        'order': 1,
        'summary': 'Understand how UTM parameters are used to attribute traffic to your account.',
        'target_roles': ['sub_publisher', 'partner_admin'],
        'content': """# UTM Tracking

UTM tracking uses URL parameters to identify which traffic belongs to you.

## How It Works

1. Your partner admin assigns you a unique UTM value (e.g., `creator_john`)
2. This value is embedded in ad tags as a GAM key-value
3. When visitors see ads, the UTM parameter tells GAM who sent the traffic
4. Revenue is attributed to you based on this parameter

## Your UTM Value

You can see your assigned UTM value on your dashboard under "Tracking Info."

## Important Notes

- UTM and subdomain tracking are mutually exclusive — you can only use one method
- Do not modify UTM parameters in ad tags, as this will break attribution
- Revenue attribution depends on correct UTM values being passed with each ad request

## How Earnings Are Calculated

```
Gross Revenue = Total ad revenue from impressions with your UTM value
Fee = Gross Revenue × Your Fee Percentage
Net Earnings = Gross Revenue - Fee
```
""",
    },
    {
        'title': 'How Subdomain Tracking Works',
        'slug': 'subdomain-tracking',
        'category': 'subdomains',
        'order': 1,
        'summary': 'Understand how subdomain-based attribution works for your traffic.',
        'target_roles': ['sub_publisher', 'partner_admin'],
        'content': """# Subdomain Tracking

Subdomain tracking uses unique subdomains to attribute traffic to your account.

## How It Works

1. Your partner admin assigns you a subdomain (e.g., `john.publisher.com`)
2. You drive traffic to this subdomain
3. GAM reports include the site/domain dimension
4. Revenue from your subdomain is attributed to you

## Your Subdomain

You can see your assigned subdomain on your dashboard under "Tracking Info."

## DNS Setup

Your partner admin handles DNS configuration. Once verified, your subdomain will be active.

## Important Notes

- Subdomain and UTM tracking are mutually exclusive — only one method per account
- Make sure all your traffic goes through your assigned subdomain
- Revenue is calculated based on impressions served on your subdomain only
""",
    },
    {
        'title': 'Understanding Your Earnings',
        'slug': 'understanding-earnings',
        'category': 'earnings',
        'order': 1,
        'summary': 'Learn how gross revenue, fees, and net earnings are calculated.',
        'target_roles': [],
        'content': """# Understanding Your Earnings

This guide explains how your earnings are calculated and displayed.

## Earnings Breakdown

| Term | Definition |
|------|-----------|
| **Gross Revenue** | Total ad revenue attributed to your traffic |
| **Fee Percentage** | The agreed-upon fee deducted from your gross revenue |
| **Fee Amount** | Gross Revenue × Fee Percentage |
| **Net Earnings** | Gross Revenue - Fee Amount (what you receive) |

## Example

If your gross revenue for a day is $100.00 and your fee is 20%:

- Gross: $100.00
- Fee: $100.00 × 20% = $20.00
- Net: $100.00 - $20.00 = **$80.00**

## Reporting Period

- Data is available daily with a 24-48 hour delay
- Monthly summaries are generated at the end of each month
- Payment processing follows the schedule agreed with your partner admin

## Data Source

All revenue data comes directly from Google Ad Manager's reporting API. The platform does not modify or estimate revenue figures.
""",
    },
    {
        'title': 'Why Only One Tracking Method?',
        'slug': 'one-tracking-method',
        'category': 'tracking',
        'order': 2,
        'summary': 'Explains the platform limitation that restricts each account to one tracking method.',
        'target_roles': ['sub_publisher', 'partner_admin'],
        'content': """# Why Only One Tracking Method?

Each sub-publisher account can use either UTM tracking OR subdomain tracking, but not both simultaneously.

## The Reason

Google Ad Manager processes reporting data using specific dimensions. When we attribute revenue to a sub-publisher, we match GAM report rows against your tracking identifier:

- **UTM**: matched against the Traffic Source dimension
- **Subdomain**: matched against the Site Name dimension

Using both methods simultaneously would create ambiguous attribution — the same impression could potentially match both a UTM value and a subdomain, leading to double-counting or conflicting data.

## Switching Methods

If you need to switch from UTM to subdomain (or vice versa), your partner admin can update your tracking method. When switching:

1. The old tracking assignment is updated
2. Historical data remains attributed to the old method
3. New data will use the new tracking method
4. There may be a brief gap during the transition

## Which Method Should I Use?

- **UTM tracking** is best if you drive traffic to the publisher's main domain
- **Subdomain tracking** is best if you operate your own subdomain of the publisher's site
""",
    },
    {
        'title': 'Partner Admin Guide',
        'slug': 'partner-admin-guide',
        'category': 'getting_started',
        'order': 2,
        'summary': 'How to manage sub-publishers, set fees, and monitor performance as a partner admin.',
        'target_roles': ['partner_admin', 'admin'],
        'content': """# Partner Admin Guide

As a partner admin, you manage sub-publishers and monitor their performance.

## Managing Sub-Publishers

### Creating a Sub-Publisher

1. Go to **Sub-Publishers** in the sidebar
2. Click **Add Sub-Publisher**
3. Fill in their details (name, email)
4. Choose a tracking method: **UTM** or **Subdomain**
5. Enter the tracking value
6. Set the fee percentage
7. Click Create

The sub-publisher will receive a welcome email with login credentials.

### Setting Fees

Each sub-publisher has a custom fee percentage (0-100%). This is the portion deducted from their gross revenue before calculating net earnings.

### Tracking Method Rules

- Each sub-publisher gets exactly ONE tracking method
- You cannot assign both UTM and subdomain to the same account
- You can switch methods, but historical data stays with the original method

## Monitoring Performance

### Partner Dashboard

Your dashboard shows:
- Total sub-publisher count
- Aggregated gross/fee/net revenue
- Per-sub-publisher performance breakdown

### Reports

Use the Reports section to see detailed breakdowns by date, filtered by individual sub-publishers.

## GAM Integration

All reporting data comes from Google Ad Manager. Reports are synced automatically. You can also trigger a manual sync from the dashboard.
""",
    },
]


class Command(BaseCommand):
    help = 'Seed tutorial/help content for the publisher dashboard'

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for item in SEED_DATA:
            obj, was_created = Tutorial.objects.update_or_create(
                slug=item['slug'],
                defaults=item,
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(self.style.SUCCESS(
            f'Tutorials seeded: {created} created, {updated} updated'
        ))
