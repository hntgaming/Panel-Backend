# gam_accounts/management/commands/test_gam.py - Complete Enhanced Version

import os
from django.core.management.base import BaseCommand
from django.conf import settings
from decouple import config
from gam_accounts.gam_config import gam_config

class Command(BaseCommand):
    help = 'Test GAM API connection and MCM functionality'
    
    def add_arguments(self, parser):
        parser.add_argument('--company-only', action='store_true', help='Test only CompanyService')
        parser.add_argument('--verbose', action='store_true', help='Show detailed output')
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write(self.style.HTTP_INFO('🔍 GAM API CONNECTION & MCM TEST'))
        self.stdout.write(self.style.HTTP_INFO('='*60))
        
        if not options['company_only']:
            # Step 1: Check environment variables
            self.test_environment_variables()
            
            # Step 2: Check service account file
            if not self.test_service_account_file():
                return
            
            # Step 3: Test basic GAM connection
            connection_result = self.test_basic_connection()
            if not connection_result['success']:
                return
        
        # Step 4: Test CompanyService for MCM functionality
        self.test_company_service(options.get('verbose', False))
        
        # Step 5: Final recommendations
        self.show_recommendations()
    
    def test_environment_variables(self):
        """Test all required environment variables"""
        self.stdout.write('\n📋 Checking Environment Variables...')
        
        required_vars = {
            'GAM_PROJECT_ID': config('GAM_PROJECT_ID', default=''),
            'GAM_PRIVATE_KEY_FILE': config('GAM_PRIVATE_KEY_FILE', default=''),
            'GAM_CLIENT_EMAIL': config('GAM_CLIENT_EMAIL', default=''),
            'GAM_PARENT_NETWORK_CODE': config('GAM_PARENT_NETWORK_CODE', default='')
        }
        
        missing_vars = []
        for var_name, var_value in required_vars.items():
            if not var_value:
                missing_vars.append(var_name)
                self.stdout.write(f"  ❌ {var_name}: Missing")
            else:
                # Mask sensitive values
                if 'KEY' in var_name:
                    display_value = f"{var_value[:20]}...{var_value[-10:]}" if len(var_value) > 30 else var_value
                else:
                    display_value = var_value
                self.stdout.write(f"  ✅ {var_name}: {display_value}")
        
        if missing_vars:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Missing environment variables: {", ".join(missing_vars)}')
            )
            self.stdout.write('Please check your .env file')
            return False
        
        self.stdout.write(self.style.SUCCESS('✅ All environment variables found'))
        return True
    
    def test_service_account_file(self):
        """Test service account file existence"""
        self.stdout.write('\n📁 Checking Service Account File...')
        
        service_account_file = config('GAM_PRIVATE_KEY_FILE', default='')
        
        # Check both absolute and relative paths
        if not os.path.isabs(service_account_file):
            service_account_file = os.path.join(settings.BASE_DIR, service_account_file)
        
        if not os.path.exists(service_account_file):
            self.stdout.write(
                self.style.ERROR(f'❌ Service account file not found: {service_account_file}')
            )
            return False
        
        # Check file size (should be reasonable for a JSON file)
        file_size = os.path.getsize(service_account_file)
        if file_size < 100:  # Too small to be a valid service account file
            self.stdout.write(
                self.style.ERROR(f'❌ Service account file seems too small: {file_size} bytes')
            )
            return False
        
        self.stdout.write(f"✅ Service account file found: {service_account_file}")
        self.stdout.write(f"   File size: {file_size} bytes")
        return True
    
    def test_basic_connection(self):
        """Test basic GAM API connection"""
        self.stdout.write('\n🌐 Testing Basic GAM Connection...')
        
        try:
            # Test with child network 22878573653 for managed account access
            result = gam_config.test_connection(network_code='22878573653')
            
            if result['success']:
                self.stdout.write(self.style.SUCCESS('✅ GAM Connection successful!'))
                self.stdout.write(f"   Network Name: {result['network_name']}")
                self.stdout.write(f"   Network Code: {result['network_code']}")
                self.stdout.write(f"   Currency: {result['currency_code']}")
                self.stdout.write(f"   Time Zone: {result.get('time_zone', 'Unknown')}")
                self.stdout.write(f"   API Version: {result.get('api_version', 'Unknown')}")
                
                if 'raw_response_type' in result:
                    self.stdout.write(f"   Response Type: {result['raw_response_type']}")
                
                return result
            else:
                self.stdout.write(self.style.ERROR(f'❌ GAM Connection failed: {result["error"]}'))
                if 'traceback' in result:
                    self.stdout.write('   Full traceback:')
                    self.stdout.write(f"   {result['traceback']}")
                return result
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error testing connection: {str(e)}'))
            import traceback
            self.stdout.write('   Full traceback:')
            self.stdout.write(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    def test_company_service(self, verbose=False):
        """Test CompanyService for MCM functionality"""
        self.stdout.write('\n🏢 Testing CompanyService (MCM Functionality)...')
        
        try:
            # Step 1: Get CompanyService for child network
            company_service = gam_config.get_service('CompanyService', network_code='22878573653')
            self.stdout.write(f"✅ CompanyService obtained: {type(company_service)}")
            
            if verbose:
                # Show available methods
                methods = [m for m in dir(company_service) if not m.startswith('_') and callable(getattr(company_service, m))]
                self.stdout.write(f"   Available methods: {methods[:10]}{'...' if len(methods) > 10 else ''}")
            
            # Step 2: Test Company SOAP element creation
            try:
                company_element = company_service.CreateSoapElementForType('Company')
                self.stdout.write('✅ Company SOAP element created successfully')
                
                # Step 3: Test setting basic Company properties
                try:
                    company_element.name = "Test MCM Company"
                    company_element.type = 'CHILD_PUBLISHER'
                    company_element.primaryEmail = 'test@example.com'
                    self.stdout.write('✅ Basic Company properties set successfully')
                    
                    if verbose:
                        # Show company element attributes
                        attrs = [attr for attr in dir(company_element) if not attr.startswith('_')]
                        self.stdout.write(f"   Company attributes: {attrs[:15]}{'...' if len(attrs) > 15 else ''}")
                    
                except Exception as props_error:
                    self.stdout.write(self.style.WARNING(f'⚠️ Setting Company properties failed: {str(props_error)}'))
                
                # Step 4: Test ChildPublisher element creation
                try:
                    child_publisher = company_service.CreateSoapElementForType('ChildPublisher')
                    self.stdout.write('✅ ChildPublisher SOAP element created successfully')
                    
                    # Test setting ChildPublisher properties
                    try:
                        child_publisher.childNetworkCode = '22878573653'
                        child_publisher.proposedDelegationType = 'MANAGE_ACCOUNT'
                        child_publisher.proposedRevenueShareMillis = 20000
                        
                        company_element.childPublisher = child_publisher
                        self.stdout.write('✅ ChildPublisher configured with MCM settings')
                        self.stdout.write('   ✓ Child Network Code: 22878573653')
                        self.stdout.write('   ✓ Delegation Type: MANAGE_ACCOUNT')
                        self.stdout.write('   ✓ Revenue Share: 20% parent, 80% child')
                        
                        if verbose:
                            child_attrs = [attr for attr in dir(child_publisher) if not attr.startswith('_')]
                            self.stdout.write(f"   ChildPublisher attributes: {child_attrs[:10]}{'...' if len(child_attrs) > 10 else ''}")
                        
                    except Exception as child_props_error:
                        self.stdout.write(self.style.WARNING(f'⚠️ Setting ChildPublisher properties failed: {str(child_props_error)}'))
                    
                except Exception as child_error:
                    self.stdout.write(self.style.ERROR(f'❌ ChildPublisher creation failed: {str(child_error)}'))
                    
                    if verbose:
                        # Try to find alternative ChildPublisher types
                        self.stdout.write('   Searching for alternative ChildPublisher types...')
                        try:
                            client = company_service.zeep_client
                            if hasattr(client.wsdl, 'types'):
                                types = list(client.wsdl.types.keys())
                                child_types = [t for t in types if 'child' in t.lower() or 'publisher' in t.lower()]
                                if child_types:
                                    self.stdout.write(f'   Found related types: {child_types}')
                        except:
                            pass
                
                # Step 5: Test if we can call createCompanies (without actually creating)
                try:
                    # Just check if the method exists and is callable
                    if hasattr(company_service, 'createCompanies'):
                        self.stdout.write('✅ createCompanies method is available')
                        self.stdout.write(self.style.SUCCESS('🎉 MCM API invitation should work!'))
                    else:
                        self.stdout.write(self.style.WARNING('⚠️ createCompanies method not found'))
                        
                except Exception as create_error:
                    self.stdout.write(self.style.WARNING(f'⚠️ createCompanies test failed: {str(create_error)}'))
                
            except Exception as soap_error:
                self.stdout.write(self.style.ERROR(f'❌ Company SOAP element creation failed: {str(soap_error)}'))
                
                # Advanced diagnostics
                if verbose:
                    self.run_advanced_diagnostics(company_service)
                
        except Exception as service_error:
            self.stdout.write(self.style.ERROR(f'❌ CompanyService failed: {str(service_error)}'))
            
            if verbose:
                # Check what other services are available
                self.check_available_services()
    
    def run_advanced_diagnostics(self, company_service):
        """Run advanced diagnostics for CompanyService issues"""
        self.stdout.write('\n🔍 Running Advanced Diagnostics...')
        
        try:
            client = company_service.zeep_client
            self.stdout.write(f'   WSDL location: {client.wsdl.location}')
            
            # Check available types
            if hasattr(client.wsdl, 'types'):
                types = list(client.wsdl.types.keys())
                self.stdout.write(f'   Available WSDL types ({len(types)}): {types[:10]}{"..." if len(types) > 10 else ""}')
                
                # Look for Company-related types
                company_types = [t for t in types if 'company' in t.lower()]
                if company_types:
                    self.stdout.write(f'   Company-related types: {company_types}')
            
            # Try different namespace variations
            namespaces_to_try = [
                'Company',
                '{https://www.google.com/apis/ads/publisher/v202505}Company',
                'ns0:Company',
                'tns:Company'
            ]
            
            self.stdout.write('   Testing different namespace variations...')
            for namespace in namespaces_to_try:
                try:
                    test_element = company_service.CreateSoapElementForType(namespace)
                    self.stdout.write(f'   ✅ Working namespace found: {namespace}')
                    break
                except Exception as ns_error:
                    self.stdout.write(f'   ❌ {namespace}: {str(ns_error)[:50]}...')
            
        except Exception as diag_error:
            self.stdout.write(f'   Diagnostics failed: {str(diag_error)}')
    
    def check_available_services(self):
        """Check what GAM services are available"""
        self.stdout.write('\n🔧 Checking Available GAM Services...')
        
        services_to_test = [
            'NetworkService',
            'InventoryService', 
            'LineItemService',
            'OrderService',
            'ReportService',
            'UserService',
            'CompanyService'
        ]
        
        working_services = []
        failed_services = []
        
        for service_name in services_to_test:
            try:
                test_service = gam_config.get_service(service_name, network_code='22878573653')
                working_services.append(service_name)
                self.stdout.write(f'   ✅ {service_name}: Available')
            except Exception as e:
                failed_services.append((service_name, str(e)[:50]))
                self.stdout.write(f'   ❌ {service_name}: {str(e)[:50]}...')
        
        self.stdout.write(f'\n   Working services ({len(working_services)}): {working_services}')
        if failed_services:
            self.stdout.write(f'   Failed services ({len(failed_services)}): {[s[0] for s in failed_services]}')
    
    def show_recommendations(self):
        """Show final recommendations based on test results"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('🎯 RECOMMENDATIONS & NEXT STEPS')
        self.stdout.write('='*60)
        
        self.stdout.write('\n💡 MCM API Status:')
        self.stdout.write('✅ If CompanyService tests passed:')
        self.stdout.write('   → API-first MCM invitations should work')
        self.stdout.write('   → Run: python manage.py debug_mcm --verbose')
        
        self.stdout.write('\n⚠️ If CompanyService tests failed:')
        self.stdout.write('   → Use manual workflow only')
        self.stdout.write('   → Run: python manage.py debug_mcm --force-manual')
        
        self.stdout.write('\n🔧 Troubleshooting Options:')
        self.stdout.write('1. Verify MCM permissions in GAM:')
        self.stdout.write('   → Admin > Account settings > MCM > Enable')
        self.stdout.write('2. Check service account permissions:')
        self.stdout.write('   → Service account needs MCM management rights')
        self.stdout.write('3. Try different API version:')
        self.stdout.write('   → Update GAM_API_VERSION in settings')
        
        self.stdout.write('\n🚀 Ready to test MCM invitations:')
        self.stdout.write('   → python manage.py debug_mcm --cleanup  # Clean old data')
        self.stdout.write('   → python manage.py debug_mcm --verbose  # Full test')
        
        self.stdout.write('\n📋 Your Business Scenario:')
        self.stdout.write('   → Parent: 152344380')
        self.stdout.write('   → Child: 22878573653 (Helal Ahmed - DP News)')
        self.stdout.write('   → Email: admin@hntgaming.me')
        self.stdout.write('   → Type: MANAGE_ACCOUNT (20% parent, 80% child)')
        
        self.stdout.write(f'\n{self.style.SUCCESS("🎉 Test Complete! Check results above.")}')