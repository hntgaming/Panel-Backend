# accounts/ads_txt_checker.py - Ads.txt verification service

import logging
import requests
from urllib.parse import urlparse, urljoin
from django.utils import timezone

logger = logging.getLogger(__name__)


class AdsTxtChecker:
    """
    Service to check and validate ads.txt files on publisher websites
    """
    
    TIMEOUT = 10  # seconds
    USER_AGENT = 'Mozilla/5.0 (compatible; ManagedInventory/1.0; +https://hntgaming.me)'
    
    @staticmethod
    def get_ads_txt_url(site_url):
        """
        Get the ads.txt URL for a given site URL
        
        Args:
            site_url: Full site URL (e.g., https://example.com)
        
        Returns:
            str: URL to ads.txt file
        """
        try:
            # Parse the URL
            parsed = urlparse(site_url)
            
            # Build ads.txt URL
            # ads.txt should be at the root: https://example.com/ads.txt
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            ads_txt_url = urljoin(base_url, '/ads.txt')
            
            return ads_txt_url
        except Exception as e:
            logger.error(f"❌ Error building ads.txt URL for {site_url}: {str(e)}")
            return None
    
    @staticmethod
    def check_ads_txt(site_url):
        """
        Check if ads.txt exists and is accessible for a given site
        
        Args:
            site_url: Full site URL (e.g., https://example.com)
        
        Returns:
            dict: {
                'success': bool,
                'exists': bool,
                'status': 'added' or 'missing',
                'url': str,
                'content': str or None,
                'error': str or None,
                'status_code': int or None
            }
        """
        ads_txt_url = AdsTxtChecker.get_ads_txt_url(site_url)
        
        if not ads_txt_url:
            return {
                'success': False,
                'exists': False,
                'status': 'missing',
                'url': None,
                'content': None,
                'error': 'Failed to build ads.txt URL',
                'status_code': None
            }
        
        try:
            # Make HTTP request to fetch ads.txt
            response = requests.get(
                ads_txt_url,
                timeout=AdsTxtChecker.TIMEOUT,
                headers={
                    'User-Agent': AdsTxtChecker.USER_AGENT
                },
                allow_redirects=True
            )
            
            # Check if request was successful
            if response.status_code == 200:
                content = response.text.strip()
                
                # Validate ads.txt content against required entries
                validation = AdsTxtChecker.validate_ads_txt_content(content, site_url)
                is_valid = validation.get('is_valid', False)
                
                # Build error message if invalid
                error_msg = None
                if not is_valid:
                    error_parts = []
                    if not validation.get('has_owner_domain'):
                        error_parts.append('Missing OWNERDOMAIN')
                    if not validation.get('has_manager_domain'):
                        error_parts.append('Missing or invalid MANAGERDOMAIN')
                    if validation.get('missing_entries'):
                        error_parts.append(f"Missing entries: {', '.join(validation['missing_entries'][:2])}")
                    if validation.get('errors'):
                        error_parts.extend(validation['errors'][:2])
                    error_msg = '; '.join(error_parts) if error_parts else 'Invalid ads.txt content'
                
                return {
                    'success': True,
                    'exists': True,
                    'status': 'added' if is_valid else 'missing',  # If invalid, treat as missing
                    'url': ads_txt_url,
                    'content': content if is_valid else None,
                    'error': error_msg,
                    'status_code': response.status_code,
                    'validation': validation
                }
            else:
                # ads.txt not found or server error
                return {
                    'success': True,
                    'exists': False,
                    'status': 'missing',
                    'url': ads_txt_url,
                    'content': None,
                    'error': f'HTTP {response.status_code}',
                    'status_code': response.status_code
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'exists': False,
                'status': 'missing',
                'url': ads_txt_url,
                'content': None,
                'error': 'Request timeout',
                'status_code': None
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'exists': False,
                'status': 'missing',
                'url': ads_txt_url,
                'content': None,
                'error': 'Connection error',
                'status_code': None
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error checking ads.txt for {site_url}: {error_msg}")
            return {
                'success': False,
                'exists': False,
                'status': 'missing',
                'url': ads_txt_url,
                'content': None,
                'error': error_msg,
                'status_code': None
            }
    
    @staticmethod
    def validate_ads_txt_content(content, site_url=None):
        """
        Validate ads.txt content against required entries
        
        Args:
            content: The content of the ads.txt file
            site_url: The site URL to extract domain for OWNERDOMAIN validation
        
        Returns:
            dict: {
                'is_valid': bool,
                'has_owner_domain': bool,
                'has_manager_domain': bool,
                'has_required_entries': bool,
                'missing_entries': list,
                'errors': list
            }
        """
        if not content or len(content.strip()) == 0:
            return {
                'is_valid': False,
                'has_owner_domain': False,
                'has_manager_domain': False,
                'has_required_entries': False,
                'missing_entries': ['ads.txt file is empty'],
                'errors': ['Empty file']
            }
        
        lines = content.strip().split('\n')
        
        # Required entries that must be present
        required_entries = [
            'ehumps.com, 23310681755, DIRECT',
            'google.com, pub-6193096344573365, DIRECT, f08c47fec0942fa0',
            'google.com, pub-6193096344573365, RESELLER, f08c47fec0942fa0'
        ]
        
        # Extract domain from site_url for OWNERDOMAIN validation
        owner_domain = None
        if site_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(site_url)
                owner_domain = parsed.netloc.replace('www.', '').lower()
            except:
                pass
        
        has_owner_domain = False
        has_manager_domain = False
        found_entries = []
        missing_entries = required_entries.copy()
        errors = []
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Check for OWNERDOMAIN
            if line.startswith('OWNERDOMAIN='):
                has_owner_domain = True
                if owner_domain:
                    # Validate OWNERDOMAIN matches site domain
                    domain_value = line.split('=', 1)[1].strip().lower()
                    domain_value = domain_value.replace('www.', '').replace('https://', '').replace('http://', '').split('/')[0]
                    if domain_value != owner_domain:
                        errors.append(f'OWNERDOMAIN mismatch: expected {owner_domain}, found {domain_value}')
                continue
            
            # Check for MANAGERDOMAIN
            if line.startswith('MANAGERDOMAIN='):
                manager_value = line.split('=', 1)[1].strip().lower()
                if manager_value == 'ehumps.com':
                    has_manager_domain = True
                else:
                    errors.append(f'MANAGERDOMAIN should be "ehumps.com", found "{manager_value}"')
                continue
            
            # Skip comments
            if line.startswith('#'):
                continue
            
            # Check for required entries (normalize for comparison)
            line_normalized = ','.join([p.strip() for p in line.split(',')[:3]])  # First 3 parts: domain, id, type
            
            for req_entry in required_entries:
                req_normalized = ','.join([p.strip() for p in req_entry.split(',')[:3]])
                if req_normalized in line_normalized or line_normalized in req_normalized:
                    if req_entry in missing_entries:
                        missing_entries.remove(req_entry)
                        found_entries.append(req_entry)
                    break
        
        # Determine if valid
        is_valid = (
            has_owner_domain and
            has_manager_domain and
            len(missing_entries) == 0 and
            len(errors) == 0
        )
        
        return {
            'is_valid': is_valid,
            'has_owner_domain': has_owner_domain,
            'has_manager_domain': has_manager_domain,
            'has_required_entries': len(missing_entries) == 0,
            'found_entries': found_entries,
            'missing_entries': missing_entries,
            'errors': errors
        }
    
    @staticmethod
    def check_all_sites():
        """
        Check ads.txt for all sites in the database
        
        Returns:
            dict: {
                'success': bool,
                'checked': int,
                'found': int,
                'missing': int,
                'errors': int,
                'error': str or None
            }
        """
        try:
            from accounts.models import Site
            
            sites = Site.objects.all()
            
            checked_count = 0
            found_count = 0
            missing_count = 0
            error_count = 0
            
            for site in sites:
                try:
                    # Check ads.txt
                    result = AdsTxtChecker.check_ads_txt(site.url)
                    
                    # Update site record
                    site.ads_txt_status = result.get('status', 'missing')
                    site.ads_txt_last_checked = timezone.now()
                    site.save(update_fields=['ads_txt_status', 'ads_txt_last_checked'])
                    
                    checked_count += 1
                    
                    if result.get('exists'):
                        found_count += 1
                        logger.info(f"✅ ads.txt found for {site.url}")
                    else:
                        missing_count += 1
                        logger.info(f"⚠️ ads.txt missing for {site.url}: {result.get('error')}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ Error checking ads.txt for site {site.id}: {str(e)}")
            
            return {
                'success': True,
                'checked': checked_count,
                'found': found_count,
                'missing': missing_count,
                'errors': error_count,
                'total': sites.count()
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to check ads.txt for all sites: {error_msg}")
            
            return {
                'success': False,
                'error': f'Failed to check ads.txt: {error_msg}',
                'checked': 0,
                'found': 0,
                'missing': 0,
                'errors': 0
            }
