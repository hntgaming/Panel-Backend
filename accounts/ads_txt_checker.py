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
                
                # Basic validation: check if it looks like an ads.txt file
                # ads.txt should contain lines with domain, publisher ID, relationship type
                is_valid = AdsTxtChecker.validate_ads_txt_content(content)
                
                return {
                    'success': True,
                    'exists': True,
                    'status': 'added' if is_valid else 'missing',  # If invalid, treat as missing
                    'url': ads_txt_url,
                    'content': content if is_valid else None,
                    'error': None if is_valid else 'Invalid ads.txt content',
                    'status_code': response.status_code
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
    def validate_ads_txt_content(content):
        """
        Basic validation of ads.txt content
        
        Args:
            content: The content of the ads.txt file
        
        Returns:
            bool: True if content looks valid
        """
        if not content or len(content.strip()) == 0:
            return False
        
        lines = content.strip().split('\n')
        valid_lines = 0
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Basic format check: should have at least domain and publisher ID
            # Format: example.com, pub-123456789, DIRECT, f08c47fec0942fa0
            parts = [p.strip() for p in line.split(',')]
            
            if len(parts) >= 2:
                # Check if first part looks like a domain
                domain = parts[0]
                if '.' in domain and len(domain) > 3:
                    valid_lines += 1
        
        # Consider valid if at least one valid line exists
        return valid_lines > 0
    
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
