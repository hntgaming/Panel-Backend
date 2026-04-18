# reports/gam_client.py - High-Performance GAM Client Service

import os
import tempfile
import threading
import yaml
from googleads import ad_manager
from google.oauth2 import service_account
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

_client_cache = {}
_client_cache_lock = threading.Lock()


class GAMClientService:
    """
    GAM client service — per-partner architecture.
    Each partner admin connects their own GAM account. Clients are cached
    per partner to avoid redundant auth handshakes across parallel workers.
    """

    @staticmethod
    def clear_client_cache():
        """Flush the cached GAM clients (useful between cron runs)."""
        with _client_cache_lock:
            _client_cache.clear()

    @staticmethod
    def get_client_for_partner(partner_admin):
        """
        Return a cached GAM AdManagerClient for a specific partner admin.

        - SERVICE_ACCOUNT: uses the shared service account key with the partner's
          network_code override (partner must add our service email as admin).
        - OAUTH2: builds credentials from the stored refresh token.
        """
        from accounts.models import GAMCredential

        try:
            cred = partner_admin.gam_credential
        except GAMCredential.DoesNotExist:
            raise ValueError(f"No GAMCredential for partner {partner_admin.email}")

        cache_key = ('partner', partner_admin.id)

        with _client_cache_lock:
            cached = _client_cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            if cred.auth_method == GAMCredential.AuthMethod.OAUTH2:
                client = GAMClientService._build_oauth_client(cred)
            else:
                client = GAMClientService._build_service_account_client(cred)

            with _client_cache_lock:
                _client_cache[cache_key] = client

            return client

        except Exception as e:
            logger.error(f"Failed to create partner GAM client for {partner_admin.email}: {e}")
            raise

    @staticmethod
    def _build_service_account_client(cred):
        """Build an AdManagerClient from the shared service account key with the partner's network code."""
        key_file = getattr(settings, 'GAM_CONFIG', {}).get('PRIVATE_KEY_FILE', '')
        key_path = os.path.join(settings.BASE_DIR, key_file) if key_file else ''

        if not key_path or not os.path.exists(key_path):
            yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
            yamls = [f for f in os.listdir(yaml_dir) if f.endswith('.yaml')] if os.path.isdir(yaml_dir) else []
            if yamls:
                key_path = os.path.join(yaml_dir, yamls[0])
            else:
                raise FileNotFoundError("No GAM service account key or YAML file found")

        if key_path.endswith('.yaml'):
            with open(key_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
            yaml_config['ad_manager']['network_code'] = int(cred.network_code)

            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tmp:
                yaml.dump(yaml_config, tmp, default_flow_style=False, indent=2)
                tmp_path = tmp.name
            try:
                client = ad_manager.AdManagerClient.LoadFromStorage(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            return client

        scopes = ['https://www.googleapis.com/auth/admanager']
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=scopes
        )
        app_name = getattr(settings, 'GAM_CONFIG', {}).get('APPLICATION_NAME', 'H&T Gaming')
        client = ad_manager.AdManagerClient(
            credentials, app_name, network_code=cred.network_code
        )
        return client

    @staticmethod
    def _build_oauth_client(cred):
        """Build an AdManagerClient using OAuth 2.0 refresh token credentials."""
        from google.oauth2.credentials import Credentials as OAuthCredentials

        oauth_creds = OAuthCredentials(
            token=None,
            refresh_token=cred.oauth_refresh_token,
            client_id=cred.oauth_client_id,
            client_secret=getattr(settings, 'GAM_OAUTH_CLIENT_SECRET', ''),
            token_uri='https://oauth2.googleapis.com/token',
        )

        application_name = getattr(settings, 'GAM_APPLICATION_NAME', settings.GAM_CONFIG['APPLICATION_NAME'])

        client = ad_manager.AdManagerClient(
            oauth_creds,
            application_name,
            network_code=cred.network_code,
        )
        return client

    @staticmethod
    def test_connection_for_partner(partner_admin):
        """Test the GAM connection for a specific partner admin."""
        try:
            GAMClientService.clear_partner_cache(partner_admin.id)
            client = GAMClientService.get_client_for_partner(partner_admin)
            network_service = client.GetService("NetworkService", version="v202508")
            current_network = network_service.getCurrentNetwork()

            return {
                'success': True,
                'network_code': str(current_network.get("networkCode", "")),
                'network_name': current_network.get("displayName", ""),
                'currency_code': current_network.get("currencyCode", "USD"),
                'time_zone': current_network.get("timeZone", "UTC"),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }

    @staticmethod
    def clear_partner_cache(partner_id):
        """Remove cached client for a specific partner."""
        cache_key = ('partner', partner_id)
        with _client_cache_lock:
            _client_cache.pop(cache_key, None)

    @staticmethod
    def get_site_status_from_gam(partner_admin, site_url=None, site_id=None, **kwargs):
        """
        Get site status from the partner's GAM network.

        Args:
            partner_admin: User object with GAMCredential
            site_url: Site URL to look up
            site_id: GAM Site ID to look up

        Returns:
            dict: {'success': bool, 'status': str, 'site_id': str, 'error': str or None}
        """
        try:
            from googleads import ad_manager
            
            client = GAMClientService.get_client_for_partner(partner_admin)
            
            # Use SiteService to get sites
            site_service = client.GetService("SiteService", version="v202511")
            
            # Build statement
            statement = ad_manager.StatementBuilder(version="v202511")
            
            if site_id:
                statement.Where("id = :site_id").WithBindVariable("site_id", int(site_id))
            elif site_url:
                # Normalize URL to domain only (GAM stores sites as "example.com" without protocol or www)
                # Extract domain from URL
                from urllib.parse import urlparse
                parsed = urlparse(site_url)
                domain = parsed.netloc or parsed.path.split('/')[0]
                # Remove www. prefix if present
                if domain.startswith('www.'):
                    domain = domain[4:]
                # Remove trailing slash if any
                domain = domain.rstrip('/')
                # Remove port if present
                if ':' in domain:
                    domain = domain.split(':')[0]
                
                # GAM stores sites as just the domain (e.g., "example.com")
                normalized_domain = domain
                
                # Try matching with the domain format
                statement.Where("url = :url").WithBindVariable("url", normalized_domain)
            else:
                return {
                    'success': False,
                    'error': 'Either site_url or site_id must be provided'
                }
            
            # Get sites
            page = site_service.getSitesByStatement(statement.ToStatement())
            
            # Handle both dict and object formats for page
            if hasattr(page, "results"):
                results = page.results
            elif isinstance(page, dict):
                results = page.get("results", [])
            else:
                results = []
            
            if not results or len(results) == 0:
                # If site not found, try alternative domain formats
                if site_url and not site_id:
                    from urllib.parse import urlparse
                    parsed = urlparse(site_url)
                    domain = parsed.netloc or parsed.path.split('/')[0]
                    
                    # Try variations: with www, without www, with protocol, etc.
                    alternative_domains = []
                    
                    # Base domain without www
                    base_domain = domain.replace('www.', '').rstrip('/')
                    if ':' in base_domain:
                        base_domain = base_domain.split(':')[0]
                    alternative_domains.append(base_domain)
                    
                    # With www
                    if not base_domain.startswith('www.'):
                        alternative_domains.append(f'www.{base_domain}')
                    
                    # Try alternative domain formats
                    for alt_domain in alternative_domains:
                        if alt_domain == normalized_domain:  # Skip if already tried
                            continue
                        try:
                            alt_statement = ad_manager.StatementBuilder(version="v202511")
                            alt_statement.Where("url = :url").WithBindVariable("url", alt_domain)
                            alt_page = site_service.getSitesByStatement(alt_statement.ToStatement())
                            
                            if hasattr(alt_page, "results"):
                                alt_results = alt_page.results
                            elif isinstance(alt_page, dict):
                                alt_results = alt_page.get("results", [])
                            else:
                                alt_results = []
                            
                            if alt_results and len(alt_results) > 0:
                                results = alt_results
                                break
                        except Exception:
                            pass
                            continue
                
                # If still not found, return error but don't set status to needs_attention
                # Let the caller decide what to do
                if not results or len(results) == 0:
                    return {
                        'success': False,
                        'error': f'Site not found in GAM (searched for: {normalized_domain})',
                        'status': None  # Don't force status change
                    }
            
            site = results[0]
            
            # Extract site data - get approvalStatus field directly
            # According to GAM API: https://developers.google.com/ad-manager/api/reference/v202511/SiteService
            # approvalStatus can be: DRAFT, UNCHECKED, APPROVED, DISAPPROVED, REQUIRES_REVIEW, UNKNOWN
            if hasattr(site, "__dict__"):  # suds object
                gam_site_id = str(getattr(site, "id", None) or "")
                approval_status = getattr(site, "approvalStatus", None)
            else:  # plain dict
                gam_site_id = str(site.get("id", "") or "")
                approval_status = site.get("approvalStatus")
            
            # Map GAM approvalStatus enum values to our 4 status values exactly as GAM UI shows them:
            # GAM API approvalStatus -> Dashboard status
            # - "Ready" = APPROVED
            # - "Getting ready" = DRAFT or UNCHECKED
            # - "Requires review" = REQUIRES_REVIEW
            # - "Needs attention" = DISAPPROVED or UNKNOWN
            
            mapped_status = 'getting_ready'  # Default for unknown cases
            
            if approval_status:
                approval_status_str = str(approval_status).upper().strip()
                
                # Map GAM API approvalStatus enum to our status values
                if approval_status_str == 'APPROVED':
                    mapped_status = 'ready'  # "Ready"
                elif approval_status_str == 'REQUIRES_REVIEW':
                    mapped_status = 'requires_review'  # "Requires review"
                elif approval_status_str in ['DRAFT', 'UNCHECKED']:
                    mapped_status = 'getting_ready'  # "Getting ready"
                elif approval_status_str in ['DISAPPROVED', 'UNKNOWN']:
                    mapped_status = 'needs_attention'  # "Needs attention"
                else:
                    # Unknown approval status - log for debugging
                    logger.warning(f"⚠️ Unknown GAM approvalStatus: '{approval_status_str}'. Defaulting to 'getting_ready'")
                    mapped_status = 'getting_ready'
            else:
                # No approval status found - default to getting_ready
                logger.warning(f"⚠️ No approvalStatus field found in GAM site object. Defaulting to 'getting_ready'")
                mapped_status = 'getting_ready'
            
            # Log the mapping
            logger.debug(f"🔍 GAM Site Status Mapping: approvalStatus='{approval_status}' -> mapped='{mapped_status}' (site_id={gam_site_id})")
            
            return {
                'success': True,
                'status': mapped_status,
                'site_id': gam_site_id,
                'gam_status': approval_status  # Original GAM approvalStatus enum value for reference
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to get site status from GAM: {error_msg}")
            
            return {
                'success': False,
                'error': f'Failed to get site status: {error_msg}',
                'status': 'needs_attention'
            }
    
    @staticmethod
    def sync_all_sites_status_from_gam():
        """
        Sync site statuses from GAM for all sites, using each site's
        partner admin's GAM credential.
        """
        try:
            from accounts.models import Site
            
            sites = Site.objects.select_related('publisher').all()
            
            synced_count = 0
            error_count = 0
            
            for site in sites:
                try:
                    partner = site.publisher
                    if site.gam_site_id:
                        result = GAMClientService.get_site_status_from_gam(partner, site_id=site.gam_site_id)
                    else:
                        result = GAMClientService.get_site_status_from_gam(partner, site_url=site.url)
                    
                    if result.get('success'):
                        new_status = result.get('status')
                        if new_status:
                            site.gam_status = new_status
                        if result.get('site_id') and not site.gam_site_id:
                            site.gam_site_id = result.get('site_id')
                        site.save(update_fields=['gam_status', 'gam_site_id'])
                        synced_count += 1
                    else:
                        error_msg = result.get('error', '').lower()
                        if 'not found' in error_msg:
                            if site.gam_status in [Site.GamStatus.ADDED, Site.GamStatus.READY]:
                                site.gam_status = Site.GamStatus.NEEDS_ATTENTION
                                site.save(update_fields=['gam_status'])
                                logger.warning(f"⚠️ Site {site.url} was marked as added/ready but not found in GAM, marking as needs_attention")
                        error_count += 1
                        logger.warning(f"⚠️ Failed to sync site {site.url}: {result.get('error')}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ Error syncing site {site.id}: {str(e)}")
            
            return {
                'success': True,
                'synced': synced_count,
                'errors': error_count,
                'total': sites.count()
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to sync sites status: {error_msg}")
            
            return {
                'success': False,
                'error': f'Failed to sync sites status: {error_msg}',
                'synced': 0,
                'errors': 0
            }
    

