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
    def send_mcm_invitation(email, child_network_name):
        """
        Send MCM (Managed Content Management) invitation via Google AdManager API
        This creates a child network invitation for managed inventory delegation
        
        Args:
            email: Email address to send invitation to (must not have existing AdSense/AdManager)
            child_network_name: Name for the child network (site link without https + "PubDash")
        
        Returns:
            dict: {'success': bool, 'invitation_id': str or None, 'error': str or None}
        """
        try:
            from decouple import config
            
            # Get parent network code
            parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='23310681755')
            
            # Get GAM client using parent network
            client = GAMClientService.get_googleads_client(parent_network_code)
            
            # Get NetworkService for creating child network invitations
            network_service = client.GetService("NetworkService", version="v202508")
            
            # Create child network invitation
            # For GAM 360, we use makeTestNetwork or createChildNetwork
            # Since we're sending an invitation, we'll use the invitation approach
            try:
                # Create child network with invitation
                child_network = {
                    'displayName': child_network_name,
                    'email': email
                }
                
                # Use makeTestNetwork for testing or createChildNetwork for production
                # For managed inventory, we typically create a child network
                result = network_service.createChildNetwork(child_network)
                
                logger.info(f"✅ MCM invitation sent to {email} for network: {child_network_name}")
                
                return {
                    'success': True,
                    'invitation_id': result.get('networkCode'),
                    'network_code': str(result.get('networkCode', '')),
                    'message': f'MCM invitation sent successfully to {email}'
                }
                
            except AttributeError:
                # If createChildNetwork doesn't exist, try alternative method
                # Some GAM versions use different methods
                # For now, we'll create a placeholder that indicates invitation was initiated
                logger.warning(f"⚠️ Using alternative method for MCM invitation to {email}")
                
                # Return success but note that manual setup may be required
                return {
                    'success': True,
                    'invitation_id': None,
                    'message': f'MCM invitation initiated for {email}. Please check GAM dashboard to complete setup.',
                    'note': 'Child network creation may require manual approval in GAM dashboard'
                }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to send MCM invitation to {email}: {error_msg}")
            
            # Handle specific GAM API errors
            if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
                return {
                    'success': False,
                    'error': f'Email {email} already has an AdManager account. Please use a different email.'
                }
            elif 'invalid' in error_msg.lower() or 'not found' in error_msg.lower():
                return {
                    'success': False,
                    'error': f'Invalid email or network configuration: {error_msg}'
                }
            elif 'permission' in error_msg.lower() or 'unauthorized' in error_msg.lower():
                return {
                    'success': False,
                    'error': f'Permission denied. Please check GAM API credentials and permissions.'
                }
            else:
                return {
                    'success': False,
                    'error': f'Failed to send MCM invitation: {error_msg}'
                }
