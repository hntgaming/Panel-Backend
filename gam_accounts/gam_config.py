import os
import tempfile
import yaml
from googleads import ad_manager
from google.oauth2 import service_account
from django.conf import settings
from decouple import config
from .constants import GAM_API_VERSION, get_service



class GAMConfig:
    def __init__(self):
        # Use config() to read from .env file (same as settings.py)
        self.project_id = config('GAM_PROJECT_ID', default='hnt-gaming')
        self.private_key_file = config('GAM_PRIVATE_KEY_FILE', default='key.json')
        self.client_email = config('GAM_CLIENT_EMAIL', default='report@hnt-gaming.iam.gserviceaccount.com')
        self.parent_network_code = config('GAM_PARENT_NETWORK_CODE', default='152344380')
        self.application_name = config('GAM_APPLICATION_NAME', default='GAM Management Platform')
        self.api_version = GAM_API_VERSION

        # GAM configuration initialized

    def get_credentials(self):
        """Get service account credentials"""
        # First try absolute path, then relative to BASE_DIR
        if os.path.isabs(self.private_key_file):
            key_file_path = self.private_key_file
        else:
            key_file_path = os.path.join(settings.BASE_DIR, self.private_key_file)
            
        if not os.path.exists(key_file_path):
            raise FileNotFoundError(f"Service account file not found: {key_file_path}")
            
        return service_account.Credentials.from_service_account_file(
            key_file_path,
            scopes=['https://www.googleapis.com/auth/dfp']
        )
    
    def get_googleads_yaml_config(self):
        """Generate googleads.yaml configuration"""
        key_file_path = self.private_key_file
        if not os.path.isabs(key_file_path):
            key_file_path = os.path.join(settings.BASE_DIR, key_file_path)
            
        return {
            'ad_manager': {
                'application_name': self.application_name,
                'network_code': self.parent_network_code,
                'path_to_private_key_file': key_file_path
            }
        }
    
    def get_ad_manager_client(self, network_code=None):
        """Initialize Ad Manager client using googleads library"""
        try:
            # Create temporary yaml config file with UTF-8 encoding
            config_data = self.get_googleads_yaml_config()
            # Always use the provided network_code for managed accounts
            if network_code:
                config_data['ad_manager']['network_code'] = network_code
            else:
                # For managed accounts, we need to specify the child network
                raise ValueError("network_code is required for managed account access")
                
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                temp_config_path = f.name
            
            try:
                # Initialize client with config file
                client = ad_manager.AdManagerClient.LoadFromStorage(temp_config_path)
                return client
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_config_path)
                except:
                    pass
                
        except Exception as e:
            raise Exception(f"Failed to initialize GAM client: {str(e)}")
    
    def get_service(self, service_name, network_code=None, version=None):
        """Get a GAM service with current API version"""
        client = self.get_ad_manager_client(network_code)
        return get_service(client, service_name, version)
    
    def test_connection(self, network_code=None):
        """Test GAM API connection with enhanced error handling"""
        try:
            # Use provided network_code or default child network for testing
            test_network_code = network_code or '22878573653'
            # Get the network service for the specific child network
            network_service = self.get_service('NetworkService', network_code=test_network_code)

            # Make the API call with timeout
            current_network = network_service.getCurrentNetwork()
            
            # Handle the response properly - it might be an object, not a dict
            if hasattr(current_network, 'displayName'):
                # It's an object with attributes
                network_name = current_network.displayName
                network_code = str(current_network.networkCode)
                currency_code = getattr(current_network, 'currencyCode', 'USD')
                time_zone = getattr(current_network, 'timeZone', 'Unknown')
            elif isinstance(current_network, dict):
                # It's a dictionary
                network_name = current_network.get('displayName', 'Unknown')
                network_code = str(current_network.get('networkCode', ''))
                currency_code = current_network.get('currencyCode', 'USD')
                time_zone = current_network.get('timeZone', 'Unknown')
            else:
                # Try to convert to dict or get string representation
                network_name = str(current_network)
                network_code = self.parent_network_code
                currency_code = 'USD'
                time_zone = 'Unknown'
            
            return {
                'success': True,
                'network_name': network_name,
                'network_code': network_code,
                'currency_code': currency_code,
                'time_zone': time_zone,
                'api_version': self.api_version,
                'raw_response_type': str(type(current_network))
            }
            
        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': str(e),
                'api_version': self.api_version,
                'traceback': traceback.format_exc()
            }

# Global instance
gam_config = GAMConfig()