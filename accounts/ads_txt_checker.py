# accounts/ads_txt_checker.py - Ads.txt verification service

import logging
import requests
from urllib.parse import urlparse, urljoin
from django.utils import timezone

logger = logging.getLogger(__name__)

MCM_PUB_ID = '6193096344573365'
OO_PUB_ID = '5954359733787559'


def _required_entries_for_pub(pub_id):
    return [
        f'google.com, pub-{pub_id}, DIRECT, f08c47fec0942fa0',
        f'google.com, pub-{pub_id}, RESELLER, f08c47fec0942fa0',
    ]


class AdsTxtChecker:
    """
    Service to check and validate ads.txt files on publisher websites.
    Uses different pub IDs depending on GAM type:
      - MCM:  pub-6193096344573365
      - O&O:  pub-5954359733787559
    """

    TIMEOUT = 10
    USER_AGENT = 'Mozilla/5.0 (compatible; HnTGaming/1.0; +https://hntgaming.me)'

    @staticmethod
    def get_ads_txt_url(site_url):
        try:
            parsed = urlparse(site_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            return urljoin(base_url, '/ads.txt')
        except Exception as e:
            logger.error(f"Error building ads.txt URL for {site_url}: {e}")
            return None

    @staticmethod
    def check_ads_txt(site_url, gam_type='mcm'):
        """
        Check if ads.txt exists and contains the correct pub ID entries.

        Args:
            site_url: Full site URL (e.g., https://example.com)
            gam_type: 'mcm' or 'o_and_o' — determines which pub ID to check
        """
        ads_txt_url = AdsTxtChecker.get_ads_txt_url(site_url)

        if not ads_txt_url:
            return {
                'success': False, 'exists': False, 'status': 'missing',
                'url': None, 'content': None,
                'error': 'Failed to build ads.txt URL', 'status_code': None,
            }

        try:
            response = requests.get(
                ads_txt_url,
                timeout=AdsTxtChecker.TIMEOUT,
                headers={'User-Agent': AdsTxtChecker.USER_AGENT},
                allow_redirects=True,
            )

            if response.status_code == 200:
                content = response.text.strip()
                validation = AdsTxtChecker.validate_ads_txt_content(content, gam_type=gam_type)
                is_valid = validation.get('is_valid', False)

                error_msg = None
                if not is_valid:
                    missing = validation.get('missing_entries', [])
                    if missing:
                        error_msg = f"Missing required entries: {', '.join(missing[:2])}"
                    else:
                        error_msg = 'Invalid ads.txt content'

                return {
                    'success': True, 'exists': True,
                    'status': 'added' if is_valid else 'missing',
                    'url': ads_txt_url,
                    'content': content if is_valid else None,
                    'error': error_msg, 'status_code': response.status_code,
                    'validation': validation,
                }
            else:
                return {
                    'success': True, 'exists': False, 'status': 'missing',
                    'url': ads_txt_url, 'content': None,
                    'error': f'HTTP {response.status_code}',
                    'status_code': response.status_code,
                }

        except requests.exceptions.Timeout:
            return {
                'success': False, 'exists': False, 'status': 'missing',
                'url': ads_txt_url, 'content': None,
                'error': 'Request timeout', 'status_code': None,
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False, 'exists': False, 'status': 'missing',
                'url': ads_txt_url, 'content': None,
                'error': 'Connection error', 'status_code': None,
            }
        except Exception as e:
            logger.error(f"Error checking ads.txt for {site_url}: {e}")
            return {
                'success': False, 'exists': False, 'status': 'missing',
                'url': ads_txt_url, 'content': None,
                'error': str(e), 'status_code': None,
            }

    @staticmethod
    def validate_ads_txt_content(content, site_url=None, gam_type='mcm'):
        """
        Validate ads.txt content against the correct pub ID for the GAM type.

        Args:
            content: Raw ads.txt file content
            site_url: Unused (kept for backward compatibility)
            gam_type: 'mcm' or 'o_and_o'
        """
        pub_id = OO_PUB_ID if gam_type == 'o_and_o' else MCM_PUB_ID
        required_entries = _required_entries_for_pub(pub_id)

        if not content or len(content.strip()) == 0:
            return {
                'is_valid': False,
                'has_owner_domain': True,
                'has_manager_domain': True,
                'has_required_entries': False,
                'missing_entries': required_entries,
                'found_entries': [],
                'errors': ['Empty file'],
            }

        lines = content.strip().split('\n')

        found_entries = []
        missing_entries = list(required_entries)

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            line_normalized = ','.join(p.strip() for p in line.split(','))

            for req_entry in required_entries:
                req_normalized = ','.join(p.strip() for p in req_entry.split(','))
                if req_normalized == line_normalized:
                    if req_entry in missing_entries:
                        missing_entries.remove(req_entry)
                        found_entries.append(req_entry)
                    break

        return {
            'is_valid': len(missing_entries) == 0,
            'has_owner_domain': True,
            'has_manager_domain': True,
            'has_required_entries': len(missing_entries) == 0,
            'found_entries': found_entries,
            'missing_entries': missing_entries,
            'errors': [],
        }

    @staticmethod
    def check_all_sites():
        """
        Check ads.txt for all sites, using the publisher's gam_type to
        determine the correct pub ID.
        """
        try:
            from accounts.models import Site

            sites = Site.objects.select_related('publisher').all()

            checked_count = 0
            found_count = 0
            missing_count = 0
            error_count = 0

            for site in sites:
                try:
                    publisher_gam_type = getattr(site.publisher, 'gam_type', 'mcm') or 'mcm'
                    result = AdsTxtChecker.check_ads_txt(site.url, gam_type=publisher_gam_type)

                    site.ads_txt_status = result.get('status', 'missing')
                    site.ads_txt_last_checked = timezone.now()
                    site.save(update_fields=['ads_txt_status', 'ads_txt_last_checked'])

                    checked_count += 1

                    if result.get('status') == 'added':
                        found_count += 1
                    else:
                        missing_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"Error checking ads.txt for site {site.id}: {e}")

            return {
                'success': True,
                'checked': checked_count,
                'found': found_count,
                'missing': missing_count,
                'errors': error_count,
                'total': sites.count(),
            }

        except Exception as e:
            logger.error(f"Failed to check ads.txt for all sites: {e}")
            return {
                'success': False,
                'error': f'Failed to check ads.txt: {e}',
                'checked': 0, 'found': 0, 'missing': 0, 'errors': 0,
            }
