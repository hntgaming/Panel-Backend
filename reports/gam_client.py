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
    
    # ------------------------------------------------------------------
    # GAM Ad Unit Hierarchy — /{networkCode}/{domain}/{SlotName}
    # Mirrors AdForge standard: domain parent + HnT slot children.
    # ------------------------------------------------------------------

    STANDARD_AD_UNITS = [
        {
            'name': 'Top_Leaderboard_ATF',
            'code': 'Top_Leaderboard_ATF',
            'description': 'Top Leaderboard',
            'sizes': [
                (300, 31), (300, 50), (300, 75), (300, 100), (300, 250),
                (320, 50), (320, 100),
                (728, 90), (728, 250),
                (970, 66), (970, 90), (970, 250),
            ],
        },
        {
            'name': 'Bottom_BTF',
            'code': 'Bottom_BTF',
            'description': 'Bottom',
            'sizes': [
                (300, 31), (300, 50), (300, 75), (300, 100), (300, 250),
                (320, 50), (320, 100),
                (728, 90), (728, 250),
                (970, 66), (970, 90), (970, 250),
            ],
        },
        {
            'name': 'Incontent_Lazy',
            'code': 'Incontent_Lazy',
            'description': 'In-Content',
            'sizes': [
                (300, 31), (300, 50), (300, 75), (300, 100), (300, 250),
                (320, 50), (320, 100),
                (250, 250), (336, 280),
                (728, 90), (728, 250), (750, 100),
            ],
        },
        {
            'name': 'Sidebar_Top_ATF',
            'code': 'Sidebar_Top_ATF',
            'description': 'Sidebar Top',
            'sizes': [
                (300, 31), (300, 50), (300, 75), (300, 100), (300, 250),
                (320, 50), (320, 100),
            ],
        },
        {
            'name': 'Sidebar_Bottom_BTF',
            'code': 'Sidebar_Bottom_BTF',
            'description': 'Sidebar Bottom',
            'sizes': [
                (300, 31), (300, 50), (300, 75), (300, 100), (300, 250),
                (320, 50), (320, 100),
                (120, 600), (160, 600), (300, 600),
            ],
        },
        {
            'name': 'Anchor_ATF',
            'code': 'Anchor_ATF',
            'description': 'Anchor',
            'sizes': [
                (300, 31), (300, 50), (300, 75), (300, 100), (300, 250),
                (320, 50), (320, 100),
                (728, 90), (970, 90),
            ],
        },
        {
            'name': 'interstitial',
            'code': 'interstitial',
            'description': 'interstitial',
            'sizes': 'OUT_OF_PAGE',
        },
        {
            'name': 'Reward',
            'code': 'Reward',
            'description': 'Reward',
            'sizes': 'OUT_OF_PAGE',
        },
        {
            'name': 'StickyOutstream',
            'code': 'StickyOutstream',
            'description': 'StickyOutstream',
            'sizes': [(300, 250)],
        },
    ]

    @staticmethod
    def _build_ad_unit_sizes(template_sizes):
        """Build adUnitSizes array for the GAM API."""
        if template_sizes == 'OUT_OF_PAGE':
            return [{
                'size': {'width': 1, 'height': 1, 'isAspectRatio': False},
                'environmentType': 'BROWSER',
                'fullDisplayString': '1x1',
            }]
        return [
            {
                'size': {'width': w, 'height': h, 'isAspectRatio': False},
                'environmentType': 'BROWSER',
            }
            for w, h in template_sizes
        ]

    @staticmethod
    def _extract_sizes(ad_unit_obj):
        """Extract (w, h) tuples from a GAM ad unit object."""
        sizes = set()
        ad_unit_sizes = getattr(ad_unit_obj, 'adUnitSizes', None) or (
            ad_unit_obj.get('adUnitSizes', []) if isinstance(ad_unit_obj, dict) else []
        )
        for aus in ad_unit_sizes:
            s = getattr(aus, 'size', None) or (aus.get('size') if isinstance(aus, dict) else None)
            if s:
                w = s.get('width') if isinstance(s, dict) else getattr(s, 'width', None)
                h = s.get('height') if isinstance(s, dict) else getattr(s, 'height', None)
                if w and h:
                    sizes.add((int(w), int(h)))
        return sizes

    @staticmethod
    def _build_size_set(template_sizes):
        if template_sizes == 'OUT_OF_PAGE':
            return {(1, 1)}
        return set(template_sizes)

    @staticmethod
    def _find_ad_unit_by_name(inventory_service, name, parent_id=None):
        """Find an ad unit by exact name, optionally scoped to a parent."""
        from googleads import ad_manager
        statement = ad_manager.StatementBuilder(version='v202511')
        if parent_id:
            statement.Where(
                'parentId = :parentId AND name = :name'
            ).WithBindVariable('parentId', int(parent_id)).WithBindVariable('name', name)
        else:
            statement.Where('name = :name').WithBindVariable('name', name)

        try:
            page = inventory_service.getAdUnitsByStatement(statement.ToStatement())
            results = getattr(page, 'results', None) or (page.get('results', []) if isinstance(page, dict) else [])
            if results:
                return results[0]
        except Exception as e:
            logger.warning('Ad unit lookup "%s" failed: %s', name, e)
        return None

    @staticmethod
    def _get_root_ad_unit_id(inventory_service):
        """Get the effective root ad unit ID for the network."""
        from googleads import ad_manager
        statement = ad_manager.StatementBuilder(version='v202511')
        statement.Where('parentId IS NULL')
        page = inventory_service.getAdUnitsByStatement(statement.ToStatement())
        results = getattr(page, 'results', None) or (page.get('results', []) if isinstance(page, dict) else [])
        if not results:
            raise RuntimeError('Cannot locate root ad unit for this network')
        unit = results[0]
        uid = getattr(unit, 'id', None) or (unit.get('id') if isinstance(unit, dict) else None)
        return str(uid)

    @staticmethod
    def _ensure_domain_parent(inventory_service, domain, root_id):
        """
        Ensure the domain-level parent ad unit exists under root.
        Returns the numeric parent ID.
        """
        existing = GAMClientService._find_ad_unit_by_name(inventory_service, domain)
        if existing:
            uid = getattr(existing, 'id', None) or (existing.get('id') if isinstance(existing, dict) else None)
            return str(uid), False

        parent_unit = {
            'name': domain,
            'adUnitCode': domain,
            'description': f'Parent ad unit for {domain}',
            'parentId': root_id,
            'targetWindow': 'BLANK',
            'adUnitSizes': [{
                'size': {'width': 300, 'height': 250, 'isAspectRatio': False},
                'environmentType': 'BROWSER',
            }],
        }
        try:
            created = inventory_service.createAdUnits([parent_unit])
            if created and len(created) > 0:
                uid = getattr(created[0], 'id', None) or (created[0].get('id') if isinstance(created[0], dict) else None)
                logger.info('Created parent ad unit "%s" -> ID %s', domain, uid)
                return str(uid), True
        except Exception as e:
            error_msg = str(e)
            if 'UniqueError' in error_msg or 'ALREADY_EXISTS' in error_msg.upper():
                retry = GAMClientService._find_ad_unit_by_name(inventory_service, domain)
                if retry:
                    uid = getattr(retry, 'id', None) or (retry.get('id') if isinstance(retry, dict) else None)
                    return str(uid), False
            raise

        return root_id, False

    @staticmethod
    def _get_or_create_ad_unit(inventory_service, parent_id, name, code=None,
                               description='', sizes=None):
        """
        Find an existing ad unit by name under parent, or create it.
        Returns (id_str, created_bool).
        """
        existing = GAMClientService._find_ad_unit_by_name(inventory_service, name, int(parent_id))
        if existing:
            eid = getattr(existing, 'id', None) or (existing.get('id') if isinstance(existing, dict) else None)
            return str(eid), False

        ad_unit = {
            'name': name,
            'adUnitCode': code or name,
            'description': description,
            'targetWindow': 'BLANK',
            'parentId': parent_id,
            'adUnitSizes': sizes or [{
                'size': {'width': 300, 'height': 250, 'isAspectRatio': False},
                'environmentType': 'BROWSER',
            }],
        }
        try:
            created = inventory_service.createAdUnits([ad_unit])
            if created and len(created) > 0:
                uid = getattr(created[0], 'id', None) or (created[0].get('id') if isinstance(created[0], dict) else None)
                return str(uid), True
        except Exception as e:
            error_msg = str(e)
            if 'UniqueError' in error_msg or 'ALREADY_EXISTS' in error_msg.upper():
                retry = GAMClientService._find_ad_unit_by_name(inventory_service, name, int(parent_id))
                if retry:
                    eid = getattr(retry, 'id', None) or (retry.get('id') if isinstance(retry, dict) else None)
                    return str(eid), False
            raise
        raise RuntimeError(f'Empty response creating ad unit "{name}"')

    @staticmethod
    def create_ad_unit_hierarchy(network_code, domain, gam_type='mcm',
                                 publisher_id=None, property_id=None,
                                 use_templates=True, custom_units=None,
                                 parent_ad_unit_id=None):
        """
        Create the 4-level ad unit hierarchy in GAM:
            root -> {domain} -> pub_{publisher_id} -> {property_id} -> {SlotName}

        Produces paths like:
            /{networkCode}/{domain}/pub_42/prop_42_example_com/Top_Leaderboard_ATF

        Idempotent: skips existing units, updates sizes if mismatched.

        Parameters
        ----------
        network_code : str
            GAM network code.
        domain : str
            Publisher domain (e.g. example.com). Top-level ad unit under root.
        gam_type : str
            'mcm' or 'o_and_o'.
        publisher_id : int or str
            Internal publisher ID for pub_{id} level.
        property_id : str
            Internal property ID for the prop_{id} level (e.g. prop_42_example_com).
        use_templates : bool
            If True, creates the standard HnT slots.
        custom_units : list[dict] or None
            Additional custom units: [{'name': ..., 'code': ..., 'sizes': [...]}].
        parent_ad_unit_id : str or None
            Override the domain parent ad unit ID.
        """
        try:
            client = GAMClientService.get_googleads_client(network_code, gam_type=gam_type)
            inventory_service = client.GetService('InventoryService', version='v202511')

            results = []
            errors = []

            # Level 1: {domain} under root
            if parent_ad_unit_id and str(parent_ad_unit_id).isdigit():
                domain_id = str(parent_ad_unit_id)
                domain_created = False
            else:
                root_id = GAMClientService._get_root_ad_unit_id(inventory_service)
                domain_id, domain_created = GAMClientService._ensure_domain_parent(
                    inventory_service, domain, root_id
                )

            results.append({
                'level': 'domain',
                'name': domain,
                'id': domain_id,
                'created': domain_created,
                'ad_unit_path': f'/{network_code}/{domain}',
            })

            # The parent for slots defaults to domain
            slot_parent_id = domain_id
            path_prefix = f'/{network_code}/{domain}'

            # Level 2: pub_{publisher_id} (if provided)
            if publisher_id is not None:
                pub_name = f'pub_{publisher_id}'
                try:
                    pub_id, pub_created = GAMClientService._get_or_create_ad_unit(
                        inventory_service, domain_id, pub_name,
                        description=f'Publisher {publisher_id}',
                    )
                    results.append({
                        'level': 'publisher',
                        'name': pub_name,
                        'id': pub_id,
                        'created': pub_created,
                        'ad_unit_path': f'{path_prefix}/{pub_name}',
                    })
                    slot_parent_id = pub_id
                    path_prefix = f'{path_prefix}/{pub_name}'
                except Exception as e:
                    return {
                        'success': False,
                        'error': f'Failed to create/find "{pub_name}" ad unit: {e}',
                        'created_units': results,
                        'errors': [str(e)],
                    }

            # Level 3: {property_id} (if provided)
            if property_id is not None:
                prop_name = str(property_id)
                if not prop_name.startswith('prop_'):
                    prop_name = f'prop_{prop_name}'
                try:
                    prop_unit_id, prop_created = GAMClientService._get_or_create_ad_unit(
                        inventory_service, slot_parent_id, prop_name,
                        description=f'Property {property_id}',
                    )
                    results.append({
                        'level': 'property',
                        'name': prop_name,
                        'id': prop_unit_id,
                        'created': prop_created,
                        'ad_unit_path': f'{path_prefix}/{prop_name}',
                    })
                    slot_parent_id = prop_unit_id
                    path_prefix = f'{path_prefix}/{prop_name}'
                except Exception as e:
                    return {
                        'success': False,
                        'error': f'Failed to create/find "{prop_name}" ad unit: {e}',
                        'created_units': results,
                        'errors': [str(e)],
                    }

            # Level 4: Standard slots (and custom units)
            units_to_create = []
            if use_templates:
                units_to_create.extend(GAMClientService.STANDARD_AD_UNITS)
            if custom_units:
                for cu in custom_units:
                    raw_sizes = cu.get('sizes', [{'width': 300, 'height': 250}])
                    if isinstance(raw_sizes, list) and raw_sizes and isinstance(raw_sizes[0], dict):
                        sizes = [(s.get('width', 300), s.get('height', 250)) for s in raw_sizes]
                    elif isinstance(raw_sizes, list) and raw_sizes and isinstance(raw_sizes[0], (list, tuple)):
                        sizes = [tuple(s) for s in raw_sizes]
                    else:
                        sizes = raw_sizes
                    units_to_create.append({
                        'name': cu['name'],
                        'code': cu.get('code', cu['name']),
                        'description': cu.get('description', ''),
                        'sizes': sizes,
                    })

            for template in units_to_create:
                tpl_name = template['name']
                tpl_code = template.get('code', tpl_name)
                full_path = f'{path_prefix}/{tpl_name}'
                try:
                    existing = GAMClientService._find_ad_unit_by_name(
                        inventory_service, tpl_name, int(slot_parent_id)
                    )

                    if existing:
                        existing_sizes = GAMClientService._extract_sizes(existing)
                        expected_sizes = GAMClientService._build_size_set(template['sizes'])

                        if existing_sizes == expected_sizes:
                            eid = getattr(existing, 'id', None) or (existing.get('id') if isinstance(existing, dict) else None)
                            results.append({
                                'level': 'slot',
                                'name': tpl_name,
                                'id': str(eid),
                                'created': False,
                                'status': 'already_exists',
                                'message': 'Sizes match — skipped',
                                'ad_unit_path': full_path,
                            })
                            continue

                        try:
                            if hasattr(existing, '__dict__'):
                                existing.adUnitSizes = GAMClientService._build_ad_unit_sizes(template['sizes'])
                            else:
                                existing['adUnitSizes'] = GAMClientService._build_ad_unit_sizes(template['sizes'])
                            inventory_service.updateAdUnits([existing])
                            eid = getattr(existing, 'id', None) or (existing.get('id') if isinstance(existing, dict) else None)
                            results.append({
                                'level': 'slot',
                                'name': tpl_name,
                                'id': str(eid),
                                'created': False,
                                'status': 'updated',
                                'message': 'Sizes updated to match template',
                                'ad_unit_path': full_path,
                            })
                        except Exception as upd_err:
                            eid = getattr(existing, 'id', None) or (existing.get('id') if isinstance(existing, dict) else None)
                            results.append({
                                'level': 'slot',
                                'name': tpl_name,
                                'id': str(eid),
                                'created': False,
                                'status': 'size_mismatch',
                                'message': f'Size update failed: {upd_err}',
                                'ad_unit_path': full_path,
                            })
                        continue

                    ad_unit = {
                        'name': tpl_name,
                        'adUnitCode': tpl_code,
                        'description': template.get('description', ''),
                        'targetWindow': 'BLANK',
                        'parentId': slot_parent_id,
                        'adUnitSizes': GAMClientService._build_ad_unit_sizes(template['sizes']),
                    }
                    created_units = inventory_service.createAdUnits([ad_unit])
                    if created_units and len(created_units) > 0:
                        unit = created_units[0]
                        uid = getattr(unit, 'id', None) or (unit.get('id') if isinstance(unit, dict) else None)
                        results.append({
                            'level': 'slot',
                            'name': tpl_name,
                            'id': str(uid),
                            'created': True,
                            'status': 'created',
                            'ad_unit_path': full_path,
                        })
                        logger.info('Created ad unit: %s (ID: %s)', tpl_name, uid)
                    else:
                        results.append({
                            'level': 'slot',
                            'name': tpl_name,
                            'id': None,
                            'created': False,
                            'status': 'empty_response',
                            'ad_unit_path': full_path,
                        })

                except Exception as e:
                    errors.append(f'{tpl_name}: {e}')
                    logger.error('Failed to process ad unit %s: %s', tpl_name, e)
                    results.append({
                        'level': 'slot',
                        'name': tpl_name,
                        'id': None,
                        'created': False,
                        'status': 'error',
                        'message': str(e)[:300],
                        'ad_unit_path': full_path,
                    })

            return {
                'success': True,
                'created_units': results,
                'errors': errors,
                'network_code': network_code,
                'domain': domain,
            }

        except Exception as e:
            logger.error(f'Failed to create ad unit hierarchy: {e}')
            return {
                'success': False,
                'error': str(e),
                'created_units': [],
                'errors': [str(e)],
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
