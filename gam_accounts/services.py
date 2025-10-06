# gam_accounts/services.py - UPDATED with Child Network Support

from googleads import ad_manager
from googleads import errors as ga_errors
from .models import GAMNetwork, MCMInvitation
from django.utils import timezone
from datetime import timedelta
import logging
import os
import yaml
import tempfile
import time
from functools import wraps
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def rate_limit_gam_api(func):
    """Decorator to rate limit GAM API calls"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Simple rate limiting using cache
        cache_key = f"gam_api_rate_limit_{func.__name__}"
        current_count = cache.get(cache_key, 0)

        if current_count >= GAMNetworkService.MAX_REQUESTS_PER_MINUTE:
            logger.warning(f"Rate limit exceeded for {func.__name__}")
            time.sleep(GAMNetworkService.RETRY_DELAY)

        # Increment counter
        cache.set(cache_key, current_count + 1, 60)  # 60 seconds TTL

        # Execute with retry logic
        for attempt in range(GAMNetworkService.MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except ga_errors.GoogleAdsError as e:
                if attempt == GAMNetworkService.MAX_RETRIES - 1:
                    raise
                logger.warning(f"GAM API error on attempt {attempt + 1}: {e}")
                time.sleep(GAMNetworkService.RETRY_DELAY * (attempt + 1))
            except Exception as e:
                if attempt == GAMNetworkService.MAX_RETRIES - 1:
                    raise
                logger.warning(f"Unexpected error on attempt {attempt + 1}: {e}")
                time.sleep(GAMNetworkService.RETRY_DELAY)

    return wrapper


class GAMNetworkService:
    """
    Enhanced service for GAM Network operations with rate limiting and error handling
    """

    # Rate limiting settings
    MAX_REQUESTS_PER_MINUTE = 100
    RETRY_DELAY = 1  # seconds
    MAX_RETRIES = 3

    @staticmethod
    def validate_yaml_config(yaml_path):
        """Validate YAML configuration file"""
        try:
            with open(yaml_path, 'r') as file:
                config = yaml.safe_load(file)

            # Check required fields
            ad_manager_fields = ['application_name', 'delegated_account', 'network_code', 'path_to_private_key_file']

            if 'ad_manager' not in config:
                raise ValueError("Missing 'ad_manager' section in YAML config")

            for field in ad_manager_fields:
                if field not in config['ad_manager']:
                    raise ValueError(f"Missing required field: ad_manager.{field}")

            # Validate private key file exists
            key_file = config['ad_manager']['path_to_private_key_file']
            if not os.path.isabs(key_file):
                key_file = os.path.join(settings.BASE_DIR, key_file)

            if not os.path.exists(key_file):
                raise ValueError(f"Private key file not found: {key_file}")

            return True

        except Exception as e:
            logger.error(f"YAML validation failed for {yaml_path}: {e}")
            raise

    @staticmethod
    @rate_limit_gam_api
    def get_googleads_client(network_code):
        """Get Google Ads client using network-specific YAML file with validation"""
        try:
            # Look for network-specific YAML file
            yaml_path = os.path.join(settings.BASE_DIR, 'yaml_files', f'{network_code}.yaml')

            if not os.path.exists(yaml_path):
                raise Exception(f"Network YAML file not found: {yaml_path}")

            # Validate YAML configuration
            GAMNetworkService.validate_yaml_config(yaml_path)

            client = ad_manager.AdManagerClient.LoadFromStorage(yaml_path)
            logger.info(f"✅ Using validated network-specific YAML: {yaml_path}")
            return client

        except Exception as e:
            logger.error(f"Failed to load network-specific client for {network_code}: {str(e)}")
            raise

    @staticmethod
    def get_googleads_client_for_child(yaml_network_code, target_network_code):
        """
        🆕 Get GAM client using specific YAML file but targeting specific network code
        Used for child networks that share service accounts but have different network codes
        
        Args:
            yaml_network_code: The network code to use for YAML file lookup
            target_network_code: The actual network code to authenticate with
        """
        import yaml
        from googleads import ad_manager
        
        # Load YAML configuration
        yaml_filepath = os.path.join(settings.BASE_DIR, 'yaml_files', f"{yaml_network_code}.yaml")
        
        if not os.path.exists(yaml_filepath):
            raise FileNotFoundError(f"YAML configuration not found: {yaml_filepath}")
        
        logger.info(f"🔑 Loading YAML config: {yaml_filepath} for target network: {target_network_code}")
        
        try:
            with open(yaml_filepath, 'r') as yaml_file:
                yaml_config = yaml.safe_load(yaml_file)
            
            # 🆕 Override the network_code with target network code
            original_network_code = yaml_config['ad_manager']['network_code']
            yaml_config['ad_manager']['network_code'] = int(target_network_code)
            
            logger.info(f"🔄 Overriding network code: {original_network_code} → {target_network_code}")
            
            # Create temporary YAML file with updated network code
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_yaml:
                yaml.dump(yaml_config, temp_yaml, default_flow_style=False, indent=2)
                temp_yaml_path = temp_yaml.name
            
            try:
                # Initialize client with temporary YAML
                client = ad_manager.AdManagerClient.LoadFromStorage(temp_yaml_path)
                logger.info(f"✅ Successfully authenticated for network {target_network_code} using {yaml_network_code}.yaml")
                return client
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_yaml_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"❌ Failed to create client for {target_network_code} using {yaml_filepath}: {str(e)}")
            raise

    @staticmethod
    def test_network_connection(network_code, yaml_network_code=None):
        """
        🆕 Test GAM API connection for a network
        
        Args:
            network_code: The network code to test
            yaml_network_code: Optional YAML file to use (defaults to network_code)
        """
        try:
            yaml_network_code = yaml_network_code or network_code
            
            # Use appropriate client method
            if yaml_network_code != network_code:
                client = GAMNetworkService.get_googleads_client_for_child(yaml_network_code, network_code)
            else:
                client = GAMNetworkService.get_googleads_client(network_code)
            
            # Test API call
            network_service = client.GetService("NetworkService", version="v202508")
            current_network = network_service.getCurrentNetwork()
            
            actual_code = str(current_network["networkCode"])
            
            if actual_code == str(network_code):
                logger.info(f"✅ Connection test successful for {network_code}")
                return {
                    'success': True,
                    'network_code': actual_code,
                    'network_name': current_network.get("displayName", ""),
                    'yaml_used': f"{yaml_network_code}.yaml"
                }
            else:
                logger.error(f"❌ Network code mismatch: expected {network_code}, got {actual_code}")
                return {
                    'success': False,
                    'error': f'Network code mismatch: expected {network_code}, got {actual_code}',
                    'yaml_used': f"{yaml_network_code}.yaml"
                }
                
        except Exception as e:
            logger.error(f"❌ Connection test failed for {network_code}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'yaml_used': f"{yaml_network_code or network_code}.yaml"
            }


class MCMService:
    """Service for MCM (Multiple Customer Management) operations"""
    
    @staticmethod
    def send_invitation_via_api(parent_network_code, child_network_code, child_network_name, 
                               primary_contact_email, delegation_type='MANAGE_INVENTORY', 
                               revenue_share_percentage=None):
        """Send MCM invitation using network-specific YAML file"""
        try:
            logger.info(f"🚀 Using network-specific YAML: {parent_network_code} → {child_network_code}")
            
            # Use network-specific YAML client
            client = GAMNetworkService.get_googleads_client(parent_network_code)
            company_service = client.GetService("CompanyService", version="v202508")
            
            # Convert percentage to millipercent (20% => 20000)
            revenue_share_millipercent = int(revenue_share_percentage * 1000) if revenue_share_percentage else 0
            
            logger.info(f"Revenue calculation: {revenue_share_percentage}% → {revenue_share_millipercent} millipercent")
            
            # Company structure
            company = {
                "name": child_network_name,
                "type": "CHILD_PUBLISHER",
                "childPublisher": {
                    "childNetworkCode": child_network_code,
                    "proposedDelegationType": delegation_type,
                    "proposedRevenueShareMillipercent": revenue_share_millipercent,
                },
                "email": primary_contact_email,
            }
            
            logger.info(f"✅ Using company structure: {company}")
            
            try:
                created_companies = company_service.createCompanies([company])
                created_company = created_companies[0]
                
                return {
                    "success": True,
                    "duplicate": False,
                    "gam_company_id": str(getattr(created_company, "id", "")),
                    "company_name": getattr(created_company, "name", child_network_name),
                    "api_method_used": f"network_yaml_{parent_network_code}",
                    "real_invitation_sent": True,
                }

            except Exception as fault:
                fault_txt = str(fault)
                if ("DUPLICATE_CHILD_PUBLISHER" in fault_txt or "UniqueError.NOT_UNIQUE" in fault_txt):
                    logger.warning("Duplicate child – treating as success")
                    existing = _get_existing_child(
                        company_service,
                        child_network_code=child_network_code,
                        email=primary_contact_email,
                        name=child_network_name,
                    )
                    return {
                        "success": True,
                        "duplicate": True,
                        "gam_company_id": str(existing.get("id")) if existing else "",
                        "company_name": existing.get("name") if existing else child_network_name,
                        "api_method_used": f"network_yaml_{parent_network_code}",
                        "real_invitation_sent": True,
                        "message": "Child already had an active or pending invitation",
                    }
                raise
                
        except Exception as e:
            logger.error(f"Network-specific YAML API failed: {str(e)}")
            return {
                'success': False,
                'error': f'Network YAML API failed: {str(e)}',
                'real_invitation_sent': False
            }
    
    @staticmethod
    def send_invitation(parent_network_code, child_network_code, child_network_name='',
                       primary_contact_email='', delegation_type='MANAGE_INVENTORY',
                       revenue_share_percentage=None, force_manual=False, invited_by=None):
        """🎯 MAIN METHOD: Send MCM invitation using network-specific YAML only"""
        try:
            # Import User model
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Get or create a default user if none provided
            if not invited_by:
                invited_by, _ = User.objects.get_or_create(
                    username='system_mcm',
                    defaults={
                        'email': 'system@mcm.com',
                        'first_name': 'MCM',
                        'last_name': 'System'
                    }
                )
            
            # Get parent network
            try:
                parent_network = GAMNetwork.objects.get(
                    network_code=parent_network_code,
                    network_type='parent'
                )
            except GAMNetwork.DoesNotExist:
                return {
                    'success': False,
                    'error': f'Parent network {parent_network_code} not found in database',
                    'no_db_record_created': True
                }
            
            # Check for existing pending invitation
            existing_invitation = MCMInvitation.objects.filter(
                parent_network=parent_network,
                child_network_code=child_network_code,
                status__in=['pending', 'awaiting_manual_send']
            ).first()
            
            if existing_invitation:
                return {
                    'success': False,
                    'error': f'Pending invitation already exists: {existing_invitation.invitation_id}',
                    'existing_invitation_id': existing_invitation.invitation_id,
                    'no_db_record_created': True
                }
            
            # Reject manual workflow
            if force_manual:
                logger.warning("❌ Manual workflow requested but disabled")
                return {
                    'success': False,
                    'error': 'Manual workflow is disabled. API invitation required.',
                    'manual_workflow_disabled': True,
                    'no_db_record_created': True
                }
            
            logger.info(f"🚀 Starting MCM invitation with {parent_network_code}.yaml → {child_network_code}")
            
            # Try network-specific YAML API
            api_result = MCMService.send_invitation_via_api(
                parent_network_code=parent_network_code,
                child_network_code=child_network_code,
                child_network_name=child_network_name,
                primary_contact_email=primary_contact_email,
                delegation_type=delegation_type,
                revenue_share_percentage=revenue_share_percentage
            )
            
            # Fail if API didn't succeed
            if not api_result or not api_result['success']:
                api_error = api_result.get('error', 'Unknown API error') if api_result else 'API result is None'
                logger.error(f"❌ Network-specific YAML failed: {api_error}")
                
                return {
                    'success': False,
                    'error': f'MCM API invitation failed: {api_error}',
                    'api_error_details': api_result.get('error') if api_result else 'No API result',
                    'troubleshooting': {
                        'issue': 'Network-specific YAML API failed',
                        'yaml_file': f'{parent_network_code}.yaml',
                        'possible_causes': [
                            f'YAML file yaml_files/{parent_network_code}.yaml not found',
                            'Service account lacks MCM permissions',
                            'Incorrect service account configuration in YAML',
                            'Child network code does not exist',
                            'Child network already has MCM relationship',
                            'Parent network MCM not enabled'
                        ],
                        'next_steps': [
                            f'Ensure yaml_files/{parent_network_code}.yaml exists',
                            'Verify YAML has correct delegated_account',
                            'Check service account permissions in Google Cloud',
                            'Verify child network code exists in GAM',
                            'Test with different child network code'
                        ]
                    },
                    'no_db_record_created': True
                }
            
            # API SUCCESS - Create DB record
            logger.info(f"✅ API invitation succeeded using {parent_network_code}.yaml!")
            status_value = "duplicate" if api_result.get("duplicate") else "pending"
            
            # Generate invitation ID
            invitation_id = f"api_success_{parent_network_code}_{child_network_code}_{int(timezone.now().timestamp())}"
            
            # Create invitation record with success data
            invitation = MCMInvitation.objects.create(
                invitation_id=invitation_id,
                parent_network=parent_network,
                child_network_code=child_network_code,
                child_network_name=child_network_name,
                primary_contact_email=primary_contact_email,
                delegation_type=delegation_type,
                revenue_share_percentage=revenue_share_percentage,
                gam_company_id=api_result['gam_company_id'],
                api_method_used=api_result['api_method_used'],
                real_invitation_sent=True,
                status=status_value,
                invited_by=invited_by,
                expires_at=timezone.now() + timedelta(days=30)
            )
            
            logger.info(f"🎉 SUCCESS: Real MCM invitation sent via {parent_network_code}.yaml and recorded in DB!")
            
            return {
                'success': True,
                'invitation': invitation,
                'real_invitation_sent': True,
                'gam_company_id': api_result['gam_company_id'],
                'company_name': api_result.get('company_name', ''),
                'message': f"🎉 REAL MCM {delegation_type} invitation sent successfully via {parent_network_code}.yaml!",
                'invitation_id': invitation.invitation_id,
                'yaml_file_used': f'{parent_network_code}.yaml',
                'next_steps': [
                    f"Child should check email at {primary_contact_email}",
                    f"Child should log into GAM network {child_network_code}",
                    "Child should go to Admin > MCM > Invitations in GAM",
                    "Child should accept the invitation",
                    "Revenue sharing will be automatic after acceptance"
                ],
                'api_method': api_result['api_method_used']
            }
                
        except Exception as e:
            logger.error(f"❌ Unexpected error in send_invitation: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'no_db_record_created': True
            }

    @staticmethod        
    def sync_invitation_statuses():
        """Sync MCM invitation statuses from GAM API using network-specific YAML"""
        updated_count = 0
        try:
            pending_invitations = MCMInvitation.objects.filter(
                status__in=['pending', 'duplicate'],
                real_invitation_sent=True,
                gam_company_id__isnull=False
            ).select_related('parent_network')

            for invitation in pending_invitations:
                try:
                    # Use network-specific YAML for each invitation
                    parent_network_code = invitation.parent_network.network_code
                    client = GAMNetworkService.get_googleads_client(parent_network_code)
                    company_service = client.GetService("CompanyService", version="v202508")

                    company_id_str = str(invitation.gam_company_id).strip()

                    if not company_id_str.isdigit():
                        logger.warning(f"⚠️ Invalid gam_company_id for invitation {invitation.id}: {invitation.gam_company_id}")
                        continue

                    statement = ad_manager.StatementBuilder(version="v202508") \
                        .Where('id = :companyId') \
                        .WithBindVariable('companyId', int(company_id_str))

                    response = company_service.getCompaniesByStatement(statement.ToStatement())
                    results = getattr(response, 'results', [])

                    if not results:
                        logger.warning(f"⚠️ No company found for GAM ID {company_id_str}")
                        continue

                    company = results[0]
                    child_publisher = getattr(company, 'childPublisher', None)
                    if not child_publisher:
                        logger.warning(f"❗ No childPublisher found in company {company.id}")
                        continue

                    # Extract values safely
                    account_status = getattr(child_publisher, 'accountStatus', None)
                    delegation_type = getattr(child_publisher, 'approvedDelegationType', None)
                    invitation_status = getattr(child_publisher, 'invitationStatus', None)

                    logger.info(
                        f"🔍 GAM company {company.id} - status: {account_status}, "
                        f"delegationType: {delegation_type}, invitationStatus: {invitation_status}, "
                        f"expected: {invitation.delegation_type}"
                    )

                    # Status update logic
                    if invitation_status == 'ACCEPTED' and delegation_type == invitation.delegation_type:
                        invitation.status = 'accepted'
                        invitation.accepted_at = timezone.now()

                    elif invitation_status == 'WITHDRAWN':
                        invitation.status = 'withdrawn'

                    elif invitation_status == 'REJECTED':
                        invitation.status = 'rejected'

                    if invitation.status in ['accepted', 'withdrawn', 'rejected']:
                        invitation.save()
                        updated_count += 1
                        logger.info(f"✅ Updated invitation {invitation.id} to '{invitation.status}'")

                except Exception as e:
                    logger.warning(f"❌ Error syncing invitation {invitation.id}: {str(e)}")

            return {
                'success': True,
                'updated_count': updated_count,
                'message': f"Synced {updated_count} invitations using network-specific YAML files"
            }

        except Exception as e:
            logger.error(f"❌ Failed to sync invitation statuses: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_existing_child(company_service, *, child_network_code=None,
                         email=None, name=None):
    """Helper function to find existing child publisher company"""
    sb = ad_manager.StatementBuilder(version="v202508")
    sb.Where("type = :ctype").WithBindVariable("ctype", "CHILD_PUBLISHER")
    page = company_service.getCompaniesByStatement(sb.ToStatement())

    # CompanyPage object or dict
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


# ============================================================================
# SERVICE SUMMARY - UPDATED
# ============================================================================

"""
🎯 NETWORK-SPECIFIC YAML SERVICE - UPDATED with Child Network Support

1. GAMNetworkService:
   ├── get_googleads_client(network_code) → Loads {network_code}.yaml
   ├── get_googleads_client_for_child(yaml_code, target_code) → 🆕 Uses YAML from one network for another
   └── test_network_connection(network_code, yaml_code) → 🆕 Test connections

2. MCMService:
   ├── send_invitation_via_api() → Uses network-specific YAML
   ├── send_invitation() → Main method, network-specific only
   └── sync_invitation_statuses() → Uses network-specific YAML per invitation

3. Helper Functions:
   └── _get_existing_child() → Used by API invitation methods

✅ NEW Features:
- get_googleads_client_for_child() for child network authentication
- Temporary YAML file creation with network code override
- Connection testing utility
- Support for both delegation types in reports

✅ Use Cases:
- MANAGE_ACCOUNT: Uses child.yaml for child network reports
- MANAGE_INVENTORY: Uses parent.yaml for parent network reports
- Cross-network authentication for reporting services
"""