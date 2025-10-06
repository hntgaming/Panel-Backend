# gam_accounts/management/commands/manage_mcm_agreements.py

from django.core.management.base import BaseCommand
from gam_accounts.services import MCMService, MCMEndAgreementService
import json

class Command(BaseCommand):
    help = 'Manage MCM agreements - list, end, and bulk operations'
    
    def add_arguments(self, parser):
        parser.add_argument('action', choices=['list', 'end', 'details', 'bulk-end'], 
                          help='Action to perform')
        
        # For 'end' action
        parser.add_argument('--company-id', type=str, help='Company ID to end agreement for')
        parser.add_argument('--child-network-code', type=str, help='Child network code to search and end')
        parser.add_argument('--email', type=str, help='Primary contact email to search and end')
        parser.add_argument('--reason', type=str, default='Manual termination via command', 
                          help='Reason for ending agreement')
        
        # For 'details' action
        parser.add_argument('--details-company-id', type=str, help='Company ID to get details for')
        
        # For 'bulk-end' action  
        parser.add_argument('--bulk-file', type=str, help='JSON file with bulk agreements to end')
        
        # General options
        parser.add_argument('--verbose', action='store_true', help='Show detailed output')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without executing')
    
    def handle(self, *args, **options):
        action = options['action']
        verbose = options['verbose']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No actions will be executed'))
        
        self.stdout.write(self.style.HTTP_INFO('='*60))
        self.stdout.write(self.style.HTTP_INFO(f'🏢 MCM AGREEMENTS MANAGEMENT - {action.upper()}'))
        self.stdout.write(self.style.HTTP_INFO('='*60))
        
        if action == 'list':
            self.handle_list_agreements(verbose)
            
        elif action == 'end':
            self.handle_end_agreement(options, dry_run, verbose)
            
        elif action == 'details':
            self.handle_company_details(options, verbose)
            
        elif action == 'bulk-end':
            self.handle_bulk_end(options, dry_run, verbose)
    
    def handle_list_agreements(self, verbose):
        """List all active MCM agreements"""
        self.stdout.write('\n📋 Fetching active MCM agreements...')
        
        try:
            result = MCMEndAgreementService.get_active_agreements()
            
            if result['success']:
                agreements = result['agreements']
                total = result['total_agreements']
                
                self.stdout.write(self.style.SUCCESS(f'✅ Found {total} active MCM agreements:'))
                
                if total == 0:
                    self.stdout.write('   No active agreements found.')
                    return
                
                # Display agreements in table format
                self.stdout.write(f'\n{"#":<3} {"Company ID":<12} {"Company Name":<25} {"Child Network":<15} {"Email":<30} {"Status":<12} {"Revenue %":<10}')
                self.stdout.write('-' * 120)
                
                for i, agreement in enumerate(agreements, 1):
                    company_id = agreement['company_id']
                    name = agreement['company_name'][:24] + ('...' if len(agreement['company_name']) > 24 else '')
                    child_network = agreement['child_network_code']
                    email = agreement['primary_contact_email'][:29] + ('...' if len(agreement['primary_contact_email']) > 29 else '')
                    status = agreement['status']
                    revenue_pct = f"{agreement['revenue_share_percentage']:.1f}%"
                    
                    self.stdout.write(f'{i:<3} {company_id:<12} {name:<25} {child_network:<15} {email:<30} {status:<12} {revenue_pct:<10}')
                
                if verbose:
                    self.stdout.write('\n📊 Detailed Agreement Information:')
                    for i, agreement in enumerate(agreements, 1):
                        self.stdout.write(f'\n🏢 Agreement {i}:')
                        self.stdout.write(f'   Company ID: {agreement["company_id"]}')
                        self.stdout.write(f'   Company Name: {agreement["company_name"]}')
                        self.stdout.write(f'   Child Network Code: {agreement["child_network_code"]}')
                        self.stdout.write(f'   Primary Email: {agreement["primary_contact_email"]}')
                        self.stdout.write(f'   Delegation Type: {agreement["delegation_type"]}')
                        self.stdout.write(f'   Status: {agreement["status"]}')
                        self.stdout.write(f'   Revenue Share: {agreement["revenue_share_percentage"]:.1f}% (parent), {100-agreement["revenue_share_percentage"]:.1f}% (child)')
                        self.stdout.write(f'   Revenue Share (millipercent): {agreement["revenue_share_millipercent"]}')
                
            else:
                self.stdout.write(self.style.ERROR(f'❌ Failed to fetch agreements: {result["error"]}'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error fetching agreements: {str(e)}'))
    
    def handle_end_agreement(self, options, dry_run, verbose):
        """End a single MCM agreement"""
        company_id = options.get('company_id')
        child_network_code = options.get('child_network_code')  
        email = options.get('email')
        reason = options.get('reason')
        
        # Validate inputs
        if not any([company_id, child_network_code, email]):
            self.stdout.write(self.style.ERROR('❌ Must provide --company-id, --child-network-code, or --email'))
            return
        
        self.stdout.write('\n🔄 Ending MCM agreement...')
        
        # Show what will be done
        if company_id:
            self.stdout.write(f'   Target: Company ID {company_id}')
        elif child_network_code:
            self.stdout.write(f'   Target: Child Network Code {child_network_code}')
        elif email:
            self.stdout.write(f'   Target: Email {email}')
        
        self.stdout.write(f'   Reason: {reason}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('   🔍 DRY RUN: Would end this agreement (not executing)'))
            return
        
        try:
            result = MCMService.end_mcm_agreement(
                company_id=company_id,
                child_network_code=child_network_code,
                primary_contact_email=email,
                reason=reason
            )
            
            if result['success']:
                self.stdout.write(self.style.SUCCESS('✅ MCM agreement ended successfully!'))
                
                if verbose:
                    self.stdout.write('\n📊 Operation Details:')
                    for key, value in result.items():
                        if key not in ['success']:
                            self.stdout.write(f'   {key}: {value}')
                            
            else:
                self.stdout.write(self.style.ERROR(f'❌ Failed to end agreement: {result["error"]}'))
                
                if verbose and 'possible_reasons' in result:
                    self.stdout.write('\n💡 Possible reasons:')
                    for reason in result['possible_reasons']:
                        self.stdout.write(f'   - {reason}')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error ending agreement: {str(e)}'))
    
    def handle_company_details(self, options, verbose):
        """Get details for a specific company"""
        company_id = options.get('details_company_id')
        
        if not company_id:
            self.stdout.write(self.style.ERROR('❌ Must provide --details-company-id'))
            return
        
        self.stdout.write(f'\n🔍 Fetching details for Company ID: {company_id}')
        
        try:
            from gam_accounts.services import GAMNetworkService
            from googleads import ad_manager
            
            client = GAMNetworkService.get_googleads_client()
            company_service = client.GetService("CompanyService", version="v202508")
            
            # Build statement
            statement_builder = ad_manager.StatementBuilder(version="v202508")
            statement_builder.Where('id = :companyId')
            statement_builder.WithBindVariable('companyId', int(company_id))
            
            # Get company
            companies_response = company_service.getCompaniesByStatement(statement_builder.ToStatement())
            
            if not companies_response.get('results'):
                self.stdout.write(self.style.ERROR(f'❌ Company with ID {company_id} not found'))
                return
            
            company = companies_response['results'][0]
            child_publisher = company.get('childPublisher', {})
            
            self.stdout.write(self.style.SUCCESS('✅ Company found!'))
            self.stdout.write('\n📊 Company Details:')
            self.stdout.write(f'   Company ID: {company["id"]}')
            self.stdout.write(f'   Company Name: {company.get("name", "Unknown")}')
            self.stdout.write(f'   Company Type: {company.get("type", "Unknown")}')
            self.stdout.write(f'   Primary Email: {company.get("email", "Unknown")}')
            
            if company.get('type') == 'CHILD_PUBLISHER':
                self.stdout.write('\n📧 Child Publisher Details:')
                self.stdout.write(f'   Child Network Code: {child_publisher.get("childNetworkCode", "N/A")}')
                self.stdout.write(f'   Delegation Type: {child_publisher.get("proposedDelegationType", "N/A")}')
                self.stdout.write(f'   Status: {child_publisher.get("status", "Unknown")}')
                revenue_millipercent = child_publisher.get("proposedRevenueShareMillipercent", 0)
                revenue_percent = revenue_millipercent / 1000 if revenue_millipercent else 0
                self.stdout.write(f'   Revenue Share: {revenue_percent:.1f}% (parent), {100-revenue_percent:.1f}% (child)')
                self.stdout.write(f'   Revenue Share (millipercent): {revenue_millipercent}')
            
            if verbose:
                self.stdout.write('\n🔧 Raw Company Data:')
                import json
                self.stdout.write(json.dumps(company, indent=2, default=str))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error fetching company details: {str(e)}'))
    
    def handle_bulk_end(self, options, dry_run, verbose):
        """Bulk end multiple MCM agreements"""
        bulk_file = options.get('bulk_file')
        
        if not bulk_file:
            self.stdout.write(self.style.ERROR('❌ Must provide --bulk-file with JSON data'))
            self.stdout.write('\n💡 Example bulk file format:')
            self.stdout.write(json.dumps({
                "agreements": [
                    {"company_id": "12345", "reason": "Contract expired"},
                    {"child_network_code": "22878573653", "reason": "Business decision"},
                    {"primary_contact_email": "test@example.com", "reason": "Account closure"}
                ]
            }, indent=2))
            return
        
        try:
            # Load bulk file
            import os
            if not os.path.exists(bulk_file):
                self.stdout.write(self.style.ERROR(f'❌ Bulk file not found: {bulk_file}'))
                return
            
            with open(bulk_file, 'r') as f:
                data = json.load(f)
            
            agreements = data.get('agreements', [])
            if not agreements:
                self.stdout.write(self.style.ERROR('❌ No agreements found in bulk file'))
                return
            
            self.stdout.write(f'\n🔄 Processing {len(agreements)} MCM agreements...')
            
            if dry_run:
                self.stdout.write(self.style.WARNING('🔍 DRY RUN: Showing what would be processed (not executing)'))
                for i, agreement in enumerate(agreements, 1):
                    self.stdout.write(f'   {i}. {agreement}')
                return
            
            # Process agreements
            successful = 0
            failed = 0
            
            for i, agreement in enumerate(agreements, 1):
                self.stdout.write(f'\n🔄 Processing agreement {i}/{len(agreements)}...')
                
                if verbose:
                    self.stdout.write(f'   Input: {agreement}')
                
                try:
                    result = MCMService.end_mcm_agreement(
                        company_id=agreement.get('company_id'),
                        child_network_code=agreement.get('child_network_code'),
                        primary_contact_email=agreement.get('primary_contact_email'),
                        reason=agreement.get('reason', f'Bulk termination #{i}')
                    )
                    
                    if result['success']:
                        successful += 1
                        self.stdout.write(self.style.SUCCESS(f'   ✅ Success: {result.get("message", "Agreement ended")}'))
                    else:
                        failed += 1
                        self.stdout.write(self.style.ERROR(f'   ❌ Failed: {result.get("error", "Unknown error")}'))
                    
                    if verbose:
                        self.stdout.write(f'   Result: {result}')
                        
                except Exception as item_error:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f'   ❌ Error: {str(item_error)}'))
            
            # Summary
            self.stdout.write('\n' + '='*60)
            self.stdout.write('📊 BULK OPERATION SUMMARY')
            self.stdout.write('='*60)
            self.stdout.write(f'Total Processed: {len(agreements)}')
            self.stdout.write(self.style.SUCCESS(f'Successful: {successful}'))
            self.stdout.write(self.style.ERROR(f'Failed: {failed}'))
            success_rate = (successful / len(agreements) * 100) if agreements else 0
            self.stdout.write(f'Success Rate: {success_rate:.1f}%')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error processing bulk file: {str(e)}'))