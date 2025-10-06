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
