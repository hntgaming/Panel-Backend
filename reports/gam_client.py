# reports/gam_client.py - High-Performance GAM Client Service

import os
import tempfile
import threading
import yaml
from googleads import ad_manager
from google.oauth2 import service_account
from django.conf import settings
from decouple import config
import logging

logger = logging.getLogger(__name__)

_client_cache = {}
_client_cache_lock = threading.Lock()


class GAMClientService:
    """
    Multi-GAM client service supporting both MCM and O&O networks.
    MCM: Uses parent YAML (GAM_PARENT_NETWORK_CODE) with child network code override.
    O&O: Uses O&O YAML (GAM_OO_NETWORK_CODE) directly on the parent network.

    Clients are cached per (gam_type, network_code) tuple to avoid redundant
    YAML I/O and OAuth handshakes across parallel workers.
    """

    @staticmethod
    def get_parent_yaml_path():
        yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
        parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='152344380')
        return os.path.join(yaml_dir, f'{parent_network_code}.yaml')

    @staticmethod
    def get_oo_yaml_path():
        yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
        oo_network_code = config('GAM_OO_NETWORK_CODE', default='23341212234')
        return os.path.join(yaml_dir, f'{oo_network_code}.yaml')

    @staticmethod
    def clear_client_cache():
        """Flush the cached GAM clients (useful between cron runs)."""
        with _client_cache_lock:
            _client_cache.clear()

    @staticmethod
    def get_googleads_client(network_code=None, gam_type='mcm'):
        """
        Return a cached (or freshly created) GAM AdManagerClient.

        For MCM publishers the parent YAML is loaded once and re-used for every
        child network because the ``network_code`` override only affects report
        scoping, not authentication.  For O&O publishers the O&O YAML is loaded
        once and shared across all O&O sites.
        """
        cache_key = (gam_type, network_code)

        with _client_cache_lock:
            cached = _client_cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            if gam_type == 'o_and_o':
                yaml_path = GAMClientService.get_oo_yaml_path()
            else:
                yaml_path = GAMClientService.get_parent_yaml_path()

            if not os.path.exists(yaml_path):
                raise FileNotFoundError(f"YAML file not found: {yaml_path}")

            with open(yaml_path, 'r') as f:
                yaml_config = yaml.safe_load(f)

            if network_code:
                yaml_config['ad_manager']['network_code'] = int(network_code)

            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_yaml:
                yaml.dump(yaml_config, temp_yaml, default_flow_style=False, indent=2)
                temp_yaml_path = temp_yaml.name

            try:
                client = ad_manager.AdManagerClient.LoadFromStorage(temp_yaml_path)
            finally:
                try:
                    os.unlink(temp_yaml_path)
                except OSError:
                    pass

            with _client_cache_lock:
                _client_cache[cache_key] = client

            return client

        except Exception as e:
            logger.error(f"Failed to create GAM client (gam_type={gam_type}): {str(e)}")
            raise
    
    @staticmethod
    def test_connection(network_code=None, gam_type='mcm'):
        """Test GAM API connection"""
        try:
            client = GAMClientService.get_googleads_client(network_code, gam_type=gam_type)
            network_service = client.GetService("NetworkService", version="v202508")
            current_network = network_service.getCurrentNetwork()
            
            return {
                'success': True,
                'network_code': str(current_network.get("networkCode", "")),
                'network_name': current_network.get("displayName", ""),
                'currency_code': current_network.get("currencyCode", "USD"),
                'time_zone': current_network.get("timeZone", "UTC")
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def send_mcm_invitation(email, child_network_name, child_network_code=None, revenue_share_percentage=None, delegation_type='MANAGE_INVENTORY'):
        """
        Send MCM (Managed Content Management) invitation via Google AdManager API
        Uses CompanyService.createCompanies() method (same as GAM-Sentinel)
        
        For Managed Inventory: No revenue share or child network code required
        
        Args:
            email: Email address to send invitation to (must not have existing AdSense/AdManager)
            child_network_name: Name for the child network (site link without https + "PubDash")
            child_network_code: Optional child network code (not required for managed inventory)
            revenue_share_percentage: Optional revenue share percentage (not used for managed inventory)
            delegation_type: Delegation type - 'MANAGE_INVENTORY' (default) or 'MANAGE_ACCOUNT'
        
        Returns:
            dict: {'success': bool, 'gam_company_id': str or None, 'error': str or None}
        """
        try:
            from decouple import config
            from googleads import ad_manager
            
            # Get parent network code
            parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='23310681755')
            
            # Get GAM client using parent network YAML
            client = GAMClientService.get_googleads_client(parent_network_code)
            
            # Use CompanyService (not NetworkService) - this is the correct API for MCM invitations
            company_service = client.GetService("CompanyService", version="v202511")
            
            # For managed inventory, revenue share is not required (set to 0)
            revenue_share_millipercent = 0
            
            
            # For managed inventory, child_network_code is optional
            # If not provided, GAM will handle it when the invitation is accepted
            # Build company structure - childPublisher is required but childNetworkCode can be omitted for MI
            child_publisher_data = {
                "proposedDelegationType": delegation_type,
                "proposedRevenueShareMillipercent": revenue_share_millipercent,
            }
            
            # Only add childNetworkCode if provided (optional for managed inventory)
            if child_network_code:
                child_publisher_data["childNetworkCode"] = child_network_code
            
            # Company structure for MCM invitation (managed inventory format)
            company = {
                "name": child_network_name,
                "type": "CHILD_PUBLISHER",
                "childPublisher": child_publisher_data,
                "email": email,
            }
            
            
            try:
                # Create company (this sends the MCM invitation)
                created_companies = company_service.createCompanies([company])
                created_company = created_companies[0]
                
                # Extract company ID (handle both dict and object formats)
                gam_company_id = None
                if hasattr(created_company, 'id'):
                    gam_company_id = str(created_company.id)
                elif isinstance(created_company, dict):
                    gam_company_id = str(created_company.get('id', ''))
                
                logger.info(f"MCM invitation sent successfully to {email} (Company ID: {gam_company_id})")
                
                return {
                    'success': True,
                    'gam_company_id': gam_company_id,
                    'company_name': child_network_name,
                    'delegation_type': delegation_type,
                    'message': f'MCM invitation sent successfully to {email}',
                    'child_network_code': child_network_code if child_network_code else None
                }
                
            except Exception as fault:
                fault_txt = str(fault)
                logger.error(f"❌ GAM API error: {fault_txt}")
                
                # Handle duplicate child publisher error (invitation already exists)
                if "DUPLICATE_CHILD_PUBLISHER" in fault_txt or "UniqueError.NOT_UNIQUE" in fault_txt:
                    logger.warning("⚠️ Duplicate child publisher - invitation may already exist")
                    
                    # Try to get existing child company (by email since child_network_code may not be available)
                    try:
                        existing = GAMClientService._get_existing_child(
                            company_service,
                            child_network_code=child_network_code,
                            email=email,
                            name=child_network_name
                        )
                        
                        if existing:
                            return {
                                'success': True,
                                'duplicate': True,
                                'gam_company_id': str(existing.get('id', '')),
                                'company_name': existing.get('name', child_network_name),
                                'message': 'Child already has an active or pending invitation',
                                'child_network_code': existing.get('childNetworkCode') if existing else child_network_code
                            }
                    except Exception as lookup_error:
                        logger.warning(f"⚠️ Could not lookup existing child: {str(lookup_error)}")
                    
                    return {
                        'success': True,
                        'duplicate': True,
                        'message': 'Child already has an active or pending invitation. Please check GAM dashboard.'
                    }
                
                # Handle other errors
                if 'already exists' in fault_txt.lower() or 'duplicate' in fault_txt.lower():
                    error_msg = f'Email {email} already has an MCM invitation.'
                    if child_network_code:
                        error_msg += f' Network {child_network_code} may also be in use.'
                    error_msg += ' Please use a different email or check GAM dashboard.'
                    return {
                        'success': False,
                        'error': error_msg
                    }
                elif 'invalid' in fault_txt.lower() or 'not found' in fault_txt.lower():
                    return {
                        'success': False,
                        'error': f'Invalid email or configuration: {fault_txt}'
                    }
                elif 'permission' in fault_txt.lower() or 'unauthorized' in fault_txt.lower():
                    return {
                        'success': False,
                        'error': f'Permission denied. Please check GAM API credentials and MCM permissions.'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Failed to send MCM invitation: {fault_txt}'
                    }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to send MCM invitation to {email}: {error_msg}")
            
            return {
                'success': False,
                'error': f'Failed to send MCM invitation: {error_msg}'
            }
    
    @staticmethod
    def _get_existing_child(company_service, *, child_network_code=None, email=None, name=None):
        """
        Helper function to find existing child publisher company
        (Copied from GAM-Sentinel reference)
        """
        from googleads import ad_manager
        
        try:
            statement = ad_manager.StatementBuilder(version="v202511")
            statement.Where("type = :ctype").WithBindVariable("ctype", "CHILD_PUBLISHER")
            page = company_service.getCompaniesByStatement(statement.ToStatement())
            
            # Handle both dict and object formats
            results = (getattr(page, "results", None) or page.get("results", []))
            
            for company in results:
                if hasattr(company, "__dict__"):  # suds object
                    cp = getattr(company, "childPublisher", None) or {}
                    child_code = getattr(cp, "childNetworkCode", None)
                    email_value = getattr(company, "email", None)
                    name_value = getattr(company, "name", None)
                    company_id = getattr(company, "id", None)
                else:  # plain dict
                    cp = company.get("childPublisher", {}) or {}
                    child_code = cp.get("childNetworkCode")
                    email_value = company.get("email")
                    name_value = company.get("name")
                    company_id = company.get("id")
                
                if ((child_network_code and child_code == child_network_code) or
                    (email and email_value == email) or
                    (name and name_value == name)):
                    
                    # Return dict format for consistent access
                    return {
                        "id": company_id,
                        "name": name_value,
                        "email": email_value,
                        "childNetworkCode": child_code
                    }
            return None
        except Exception as e:
            logger.error(f"❌ Error looking up existing child: {str(e)}")
            return None
    
    @staticmethod
    def add_site_to_parent_network(site_url, site_name=None, child_network_code=None, gam_type='mcm'):
        """
        Add a site to the appropriate GAM network via API.
        MCM: adds to MCM parent network. O&O: adds to O&O network.
        """
        try:
            from decouple import config
            from googleads import ad_manager
            
            if gam_type == 'o_and_o':
                target_network_code = config('GAM_OO_NETWORK_CODE', default='23341212234')
            else:
                target_network_code = config('GAM_PARENT_NETWORK_CODE', default='23310681755')
            
            client = GAMClientService.get_googleads_client(target_network_code, gam_type=gam_type)
            
            # Use SiteService to create sites
            site_service = client.GetService("SiteService", version="v202511")
            
            # Extract domain from URL for site name if not provided
            if not site_name:
                # Remove protocol
                domain = site_url.replace('https://', '').replace('http://', '')
                # Remove trailing slash
                domain = domain.rstrip('/')
                # Remove www. if present
                if domain.startswith('www.'):
                    domain = domain[4:]
                site_name = domain
            
            # Normalize site URL to domain format (GAM stores sites as "example.com" without protocol or www)
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
            
            # Build site structure
            # Note: Sites in parent network cannot directly set childNetworkCode
            # The association happens through MCM relationship after invitation acceptance
            site = {
                "url": normalized_domain,
            }
            
            
            try:
                # Create site(s)
                created_sites = site_service.createSites([site])
                created_site = created_sites[0]
                
                # Extract site ID (handle both dict and object formats)
                site_id = None
                if hasattr(created_site, 'id'):
                    site_id = str(created_site.id)
                elif isinstance(created_site, dict):
                    site_id = str(created_site.get('id', ''))
                
                logger.info(f"Site added successfully to GAM: {normalized_domain} (Site ID: {site_id})")
                
                return {
                    'success': True,
                    'site_id': site_id,
                    'site_url': normalized_domain,  # Return domain format
                    'site_name': site_name,
                    'message': f'Site {normalized_domain} added successfully to parent GAM network',
                    'child_network_code': child_network_code if child_network_code else None
                }
                
            except Exception as fault:
                fault_txt = str(fault)
                logger.error(f"❌ GAM API error adding site: {fault_txt}")
                
                # Handle duplicate site error
                if "DUPLICATE" in fault_txt.upper() or "already exists" in fault_txt.lower():
                    logger.warning("⚠️ Site may already exist in GAM")
                    
                    # Try to find existing site
                    try:
                        existing = GAMClientService._get_existing_site(
                            site_service,
                            site_url=normalized_domain
                        )
                        
                        if existing:
                            return {
                                'success': True,
                                'duplicate': True,
                                'site_id': str(existing.get('id', '')),
                                'site_url': existing.get('url', normalized_domain),
                                'message': 'Site already exists in GAM network',
                                'child_network_code': existing.get('childNetworkCode') if existing else child_network_code
                            }
                    except Exception as lookup_error:
                        logger.warning(f"⚠️ Could not lookup existing site: {str(lookup_error)}")
                    
                    return {
                        'success': True,
                        'duplicate': True,
                        'message': 'Site already exists in GAM network. Please check GAM dashboard.'
                    }
                
                # Handle other errors
                if 'invalid' in fault_txt.lower() or 'not found' in fault_txt.lower():
                    return {
                        'success': False,
                        'error': f'Invalid site URL or configuration: {fault_txt}'
                    }
                elif 'permission' in fault_txt.lower() or 'unauthorized' in fault_txt.lower():
                    return {
                        'success': False,
                        'error': f'Permission denied. Please check GAM API credentials and site management permissions.'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Failed to add site: {fault_txt}'
                    }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to add site {site_url}: {error_msg}")
            
            return {
                'success': False,
                'error': f'Failed to add site: {error_msg}'
            }
    
    @staticmethod
    def _get_existing_site(site_service, *, site_url=None):
        """
        Helper function to find existing site by URL
        """
        from googleads import ad_manager
        from urllib.parse import urlparse
        
        try:
            statement = ad_manager.StatementBuilder(version="v202511")
            if site_url:
                # Normalize to domain format (GAM stores as "example.com")
                parsed = urlparse(site_url) if '://' in site_url else None
                if parsed:
                    domain = parsed.netloc or parsed.path.split('/')[0]
                else:
                    domain = site_url
                
                # Remove www. prefix if present
                if domain.startswith('www.'):
                    domain = domain[4:]
                
                # Remove trailing slash and port
                domain = domain.rstrip('/')
                if ':' in domain:
                    domain = domain.split(':')[0]
                
                normalized_domain = domain
                statement.Where("url = :url").WithBindVariable("url", normalized_domain)
            
            page = site_service.getSitesByStatement(statement.ToStatement())
            
            # Handle both dict and object formats
            results = (getattr(page, "results", None) or page.get("results", []))
            
            if results and len(results) > 0:
                site = results[0]
                
                # Return dict format for consistent access
                if hasattr(site, "__dict__"):  # suds object
                    return {
                        "id": getattr(site, "id", None),
                        "url": getattr(site, "url", None),
                        "childNetworkCode": getattr(getattr(site, "childNetworkCode", None), "value", None) if hasattr(site, "childNetworkCode") else None
                    }
                else:  # plain dict
                    return {
                        "id": site.get("id"),
                        "url": site.get("url"),
                        "childNetworkCode": site.get("childNetworkCode")
                    }
            
            return None
        except Exception as e:
            logger.error(f"❌ Error looking up existing site: {str(e)}")
            return None
    
    @staticmethod
    def get_site_status_from_gam(site_url=None, site_id=None, gam_type='mcm'):
        """
        Get site status from GAM API
        
        Args:
            site_url: Site URL to look up
            site_id: GAM Site ID to look up
            gam_type: 'mcm' or 'o_and_o'
        
        Returns:
            dict: {'success': bool, 'status': str, 'site_id': str, 'error': str or None}
        """
        try:
            from decouple import config
            from googleads import ad_manager
            
            if gam_type == 'o_and_o':
                target_network_code = config('GAM_OO_NETWORK_CODE', default='23341212234')
            else:
                target_network_code = config('GAM_PARENT_NETWORK_CODE', default='23310681755')
            
            client = GAMClientService.get_googleads_client(target_network_code, gam_type=gam_type)
            
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
        Sync site statuses from GAM for all sites in the database
        
        Returns:
            dict: {'success': bool, 'synced': int, 'errors': int, 'error': str or None}
        """
        try:
            from accounts.models import Site
            
            # Get all sites
            sites = Site.objects.all()
            
            synced_count = 0
            error_count = 0
            
            for site in sites:
                try:
                    publisher_gam_type = getattr(site.publisher, 'gam_type', 'mcm') or 'mcm'

                    if publisher_gam_type == 'o_and_o':
                        if site.gam_site_id:
                            if site.gam_status != Site.GamStatus.READY:
                                site.gam_status = Site.GamStatus.READY
                                site.save(update_fields=['gam_status'])
                            synced_count += 1
                            continue
                        result = GAMClientService.get_site_status_from_gam(site_url=site.url, gam_type=publisher_gam_type)
                        update_fields = []
                        if result.get('success') and result.get('site_id'):
                            site.gam_site_id = result['site_id']
                            update_fields.append('gam_site_id')
                        if site.gam_status != Site.GamStatus.READY:
                            site.gam_status = Site.GamStatus.READY
                            update_fields.append('gam_status')
                        if update_fields:
                            site.save(update_fields=update_fields)
                        synced_count += 1
                        continue

                    if site.gam_site_id:
                        result = GAMClientService.get_site_status_from_gam(site_id=site.gam_site_id, gam_type=publisher_gam_type)
                    else:
                        result = GAMClientService.get_site_status_from_gam(site_url=site.url, gam_type=publisher_gam_type)
                    
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
    
    @staticmethod
    def fetch_network_ids_for_publishers(publisher_emails):
        """
        Fetch network IDs from GAM for multiple publishers by their email addresses
        
        Args:
            publisher_emails: List of email addresses to look up
        
        Returns:
            dict: {'success': bool, 'results': [{'email': str, 'network_id': str or None}], 'error': str or None}
        """
        try:
            from decouple import config
            from googleads import ad_manager
            
            # Get parent network code
            parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='23310681755')
            
            # Get GAM client using parent network YAML
            client = GAMClientService.get_googleads_client(parent_network_code)
            
            # Use CompanyService to get child publishers
            company_service = client.GetService("CompanyService", version="v202511")
            
            # Build statement to get all child publishers
            statement = ad_manager.StatementBuilder(version="v202511")
            statement.Where("type = :ctype").WithBindVariable("ctype", "CHILD_PUBLISHER")
            
            # Get all child publishers
            page = company_service.getCompaniesByStatement(statement.ToStatement())
            
            # Handle both dict and object formats
            results = (getattr(page, "results", None) or page.get("results", []))
            
            # Create a mapping of email to network_id
            email_to_network = {}
            for company in results:
                if hasattr(company, "__dict__"):  # suds object
                    cp = getattr(company, "childPublisher", None) or {}
                    child_code = getattr(cp, "childNetworkCode", None)
                    email_value = getattr(company, "email", None)
                else:  # plain dict
                    cp = company.get("childPublisher", {}) or {}
                    child_code = cp.get("childNetworkCode")
                    email_value = company.get("email")
                
                if email_value and child_code:
                    # Normalize email to lowercase for matching
                    email_to_network[email_value.lower()] = str(child_code)
            
            # Match publisher emails with network IDs
            matched_results = []
            for email in publisher_emails:
                normalized_email = email.lower() if email else None
                network_id = email_to_network.get(normalized_email) if normalized_email else None
                matched_results.append({
                    'email': email,
                    'network_id': network_id
                })
            
            logger.info(f"Fetched network IDs: {sum(1 for r in matched_results if r['network_id'])} found out of {len(matched_results)} publishers")
            
            return {
                'success': True,
                'results': matched_results,
                'total_checked': len(publisher_emails),
                'total_found': sum(1 for r in matched_results if r['network_id'])
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to fetch network IDs from GAM: {error_msg}")
            
            return {
                'success': False,
                'error': f'Failed to fetch network IDs: {error_msg}',
                'results': []
            }
