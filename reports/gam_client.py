# reports/gam_client.py - Simplified GAM Client Service

import os
import tempfile
import yaml
from googleads import ad_manager
from google.oauth2 import service_account
from django.conf import settings
from decouple import config
import logging

logger = logging.getLogger(__name__)


class GAMClientService:
    """
    Simplified GAM client service for managed inventory reports
    Uses parent YAML configuration for all networks
    """
    
    @staticmethod
    def get_parent_yaml_path():
        """Get the parent YAML file path"""
        yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
        parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='152344380')
        return os.path.join(yaml_dir, f'{parent_network_code}.yaml')
    
    @staticmethod
    def get_googleads_client(network_code=None):
        """
        Get GAM client using parent YAML configuration
        For managed inventory, we use the parent network configuration
        """
        try:
            # Use parent YAML file for all managed inventory operations
            yaml_path = GAMClientService.get_parent_yaml_path()
            
            if not os.path.exists(yaml_path):
                raise FileNotFoundError(f"Parent YAML file not found: {yaml_path}")
            
            # Load and validate YAML configuration
            with open(yaml_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
            
            # Override network code if provided
            if network_code:
                original_network_code = yaml_config['ad_manager']['network_code']
                yaml_config['ad_manager']['network_code'] = int(network_code)
                logger.info(f"🔄 Using parent YAML for network {network_code} (original: {original_network_code})")
            
            # Create temporary YAML file with updated network code
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_yaml:
                yaml.dump(yaml_config, temp_yaml, default_flow_style=False, indent=2)
                temp_yaml_path = temp_yaml.name
            
            try:
                # Initialize client with temporary YAML
                client = ad_manager.AdManagerClient.LoadFromStorage(temp_yaml_path)
                logger.info(f"✅ GAM client created for network {network_code or 'parent'}")
                return client
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_yaml_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"❌ Failed to create GAM client: {str(e)}")
            raise
    
    @staticmethod
    def test_connection(network_code=None):
        """Test GAM API connection"""
        try:
            client = GAMClientService.get_googleads_client(network_code)
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
            
            logger.info(f"📊 Managed Inventory invitation - no revenue share required")
            
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
                logger.info(f"📋 Using provided child network code: {child_network_code}")
            else:
                logger.info(f"📋 No child network code provided - GAM will handle during invitation acceptance")
            
            # Company structure for MCM invitation (managed inventory format)
            company = {
                "name": child_network_name,
                "type": "CHILD_PUBLISHER",
                "childPublisher": child_publisher_data,
                "email": email,
            }
            
            logger.info(f"🚀 Sending MCM invitation with company structure: {company}")
            
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
                
                logger.info(f"✅ MCM invitation sent successfully to {email}")
                logger.info(f"   GAM Company ID: {gam_company_id}")
                logger.info(f"   Delegation Type: {delegation_type}")
                if child_network_code:
                    logger.info(f"   Child Network: {child_network_code}")
                
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
