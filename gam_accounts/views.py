# gam_accounts/views.py - UPDATED WITH YAML FILE MANAGEMENT

from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.utils import timezone
from django.db.models import Count, Q
import logging

from .models import AssignedPartnerChildAccount, GAMNetwork, MCMInvitation
from .serializers import (
    AddChildAccountSerializer, AssignPartnerToChildSerializer, GAMNetworkSerializer, 
    GAMNetworkListSerializer, MCMInvitationSerializer, MCMInvitationUpdateSerializer, 
    MCMInvitationUserStatusUpdateSerializer, SendMCMInvitationSerializer, MCMInvitationStatusSerializer, 
    MCMInvitationListSerializer, ParentGAMUserCreateSerializer
)
from .services import MCMService
from accounts.models import User
from accounts.permissions import PartnerQuerysetMixin, PermissionType, has_partner_permission, can_modify_gam_status
from django.conf import settings
import yaml
import os

logger = logging.getLogger(__name__)

# ============================================================================
# YAML HELPER METHODS
# ============================================================================

def create_child_yaml_file(invitation):
    """Create YAML configuration file for child network"""
    # Ensure yaml_files directory exists
    yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
    os.makedirs(yaml_dir, exist_ok=True)
    
    # Create YAML file named by child network code
    yaml_filepath = os.path.join(yaml_dir, f"{invitation.child_network_code}.yaml")
    
    # Create YAML content with child network code
    yaml_content = {
        'ad_manager': {
            'application_name': 'GAM Management Platform',
            'network_code': int(invitation.child_network_code),  # Ensure integer
            'path_to_private_key_file': 'key.json',
            'delegated_account': 'report@hnt-gaming.iam.gserviceaccount.com'
        }
    }
    
    try:
        with open(yaml_filepath, 'w') as yaml_file:
            yaml.dump(yaml_content, yaml_file, default_flow_style=False, indent=2)
        logger.info(f"Created YAML file for child network: {invitation.child_network_code}")
        return True
    except Exception as e:
        logger.error(f"Failed to create YAML file for {invitation.child_network_code}: {str(e)}")
        return False


def delete_child_yaml_file(child_network_code):
    """Delete YAML configuration file for child network"""
    yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
    yaml_filepath = os.path.join(yaml_dir, f"{child_network_code}.yaml")
    
    try:
        if os.path.exists(yaml_filepath):
            os.remove(yaml_filepath)
            logger.info(f"Deleted YAML file for child network: {child_network_code}")
            return True
        else:
            logger.warning(f"YAML file not found for child network: {child_network_code}")
            return False
    except Exception as e:
        logger.error(f"Failed to delete YAML file for {child_network_code}: {str(e)}")
        return False

# ============================================================================
# GAM NETWORK VIEWS (UNCHANGED)
# ============================================================================

class GAMNetworkListCreateView(ListCreateAPIView):
    """
    GET  /api/gam/networks/ - List all networks with filtering
    POST /api/gam/networks/ - Create new network
    """
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return GAMNetworkListSerializer
        return GAMNetworkSerializer
    
    def get_queryset(self):
        queryset = GAMNetwork.objects.all()
        
        # Filter by network type
        network_type = self.request.query_params.get('type', None)
        if network_type in ['parent', 'child']:
            queryset = queryset.filter(network_type=network_type)
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Search across multiple fields
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(network_name__icontains=search) |
                Q(network_code__icontains=search) |
                Q(display_name__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def create(self, request, *args, **kwargs):
        """Override create to generate YAML file for parent networks"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Save the network instance
        network = serializer.save()
        
        # Generate YAML file if it's a parent network
        if network.network_type == 'parent':
            self.create_parent_yaml_file(network)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def create_parent_yaml_file(self, network):
        """Create YAML configuration file for parent network"""
        # Ensure yaml_files directory exists
        yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
        os.makedirs(yaml_dir, exist_ok=True)
        
        # Create YAML file
        yaml_filepath = os.path.join(yaml_dir, f"{network.network_code}.yaml")
        
        # Create YAML content with proper structure
        yaml_content = {
        'ad_manager': {
            'application_name': 'GAM Management Platform',
            'network_code': int(network.network_code),  # Ensure integer
            'path_to_private_key_file': 'key.json',
            'delegated_account': network.service_account_email or 'report@hnt-gaming.iam.gserviceaccount.com'
            }
        }
        
        with open(yaml_filepath, 'w') as yaml_file:
            yaml.dump(yaml_content, yaml_file, default_flow_style=False, indent=2)


class GAMNetworkDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET    /api/gam/networks/{id}/ - Get network details
    PUT    /api/gam/networks/{id}/ - Update network (full)
    PATCH  /api/gam/networks/{id}/ - Update network (partial)
    DELETE /api/gam/networks/{id}/ - Delete network
    """
    queryset = GAMNetwork.objects.all()
    serializer_class = GAMNetworkSerializer
    permission_classes = [IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        """Override destroy to clean up YAML file for parent networks"""
        instance = self.get_object()
        network_code = instance.network_code
        is_parent = instance.network_type == 'parent'
        
        # Delete the network
        self.perform_destroy(instance)
        
        # Clean up YAML file if it was a parent network
        if is_parent:
            yaml_dir = os.path.join(settings.BASE_DIR, 'yaml_files')
            yaml_filepath = os.path.join(yaml_dir, f"{network_code}.yaml")
            
            if os.path.exists(yaml_filepath):
                os.remove(yaml_filepath)
        
        return Response({
            'success': True,
            'message': f'Network {network_code} deleted successfully'
        }, status=status.HTTP_200_OK)

# ============================================================================
# MCM INVITATION VIEWS (UPDATED WITH YAML SUPPORT)
# ============================================================================

class MCMInvitationListCreateView(ListCreateAPIView):
    """
    GET  /api/gam/mcm-invitations/ - List all invitations with filtering
    POST /api/gam/mcm-invitations/ - Create invitation record
    
    Partners see only assigned accounts
    Admins see all accounts
    """
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return MCMInvitationListSerializer
        return MCMInvitationSerializer
    
    def get_queryset(self):
        from accounts.rbac_service import RBACService
        
        queryset = MCMInvitation.objects.select_related('parent_network', 'invited_by')
        
        # Apply RBAC scope filtering
        scope = RBACService.get_user_scope(self.request.user)
        
        if self.request.user.role.upper() == 'PARENT':
            # Parent users see accounts from their assigned parent network
            if scope.get('parent_network_id'):
                queryset = queryset.filter(parent_network_id=scope['parent_network_id'])
            else:
                queryset = queryset.none()  # No parent network assigned, show nothing
        
        elif self.request.user.role.upper() == 'PARTNER':
            # Partner users see only assigned accounts
            publisher_ids = scope.get('publisher_ids', [])
            if publisher_ids:
                queryset = queryset.filter(id__in=publisher_ids)
            else:
                queryset = queryset.none()  # No assigned accounts, show nothing
        
        # Status filter
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Parent network filter
        parent_network = self.request.query_params.get('parent_network', None)
        if parent_network:
            queryset = queryset.filter(parent_network__network_code=parent_network)
        
        # Delegation type filter
        delegation_type = self.request.query_params.get('delegation_type', None)
        if delegation_type:
            queryset = queryset.filter(delegation_type=delegation_type)
        
        # API vs manual filter
        real_invitation = self.request.query_params.get('real_invitation_sent', None)
        if real_invitation is not None:
            queryset = queryset.filter(real_invitation_sent=real_invitation.lower() == 'true')
        
        # Date filters
        created_after = self.request.query_params.get('created_after', None)
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        
        created_before = self.request.query_params.get('created_before', None)
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        
        # Search filter - search across multiple fields
        search_term = self.request.query_params.get('search', None)
        if search_term:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(child_network_name__icontains=search_term) |
                Q(primary_contact_email__icontains=search_term) |
                Q(child_network_code__icontains=search_term)
            )
        
        return queryset.order_by('-created_at')


class MCMInvitationDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET    /api/gam/mcm-invitations/{id}/ - Get invitation details
    PUT    /api/gam/mcm-invitations/{id}/ - Update invitation (full)
    PATCH  /api/gam/mcm-invitations/{id}/ - Update invitation (partial)
    DELETE /api/gam/mcm-invitations/{id}/ - Delete invitation
    """
    queryset = MCMInvitation.objects.all()
    serializer_class = MCMInvitationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return MCMInvitationStatusSerializer
        return MCMInvitationSerializer


class SendMCMInvitationView(APIView):
    """
    POST /api/gam/mcm-invitations/send-invitation/ - Send REAL MCM invitation
    UPDATED: Creates YAML file when real_invitation_sent=True
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = SendMCMInvitationSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Extract validated data
                data = serializer.validated_data
                
                # Call enhanced MCM service with API support
                result = MCMService.send_invitation(
                    parent_network_code=data['parent_network_code'],
                    child_network_code=data['child_network_code'],
                    child_network_name=data.get('child_network_name', ''),
                    primary_contact_email=data['primary_contact_email'],
                    delegation_type=data['delegation_type'],
                    revenue_share_percentage=data.get('revenue_share_percentage'),
                    force_manual=data.get('force_manual', False),
                    invited_by=request.user
                )
                
                if result['success']:
                    invitation = result['invitation']
                    invitation_serializer = MCMInvitationStatusSerializer(invitation)
                    
                    # 🆕 CREATE YAML FILE WHEN REAL INVITATION IS SENT
                    yaml_created = False
                    if result.get('real_invitation_sent', False):
                        yaml_created = create_child_yaml_file(invitation)
                    
                    response_data = {
                        'success': True,
                        'real_invitation_sent': result.get('real_invitation_sent', False),
                        'invitation_id': result['invitation'].invitation_id,
                        'invitation': invitation_serializer.data,
                        'gam_company_id': result.get('gam_company_id', ''),
                        'yaml_file_used': result.get('yaml_file_used', ''),
                        'yaml_file_created': yaml_created,  # 🆕 Include YAML creation status
                        'message': result['message']
                    }
                    
                    return Response(response_data, status=status.HTTP_201_CREATED)
                    
                else:
                    return Response({
                        'success': False,
                        'error': result['error'],
                        'troubleshooting': result.get('troubleshooting', {})
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
            except Exception as e:
                logger.error(f"Error sending MCM invitation: {str(e)}")
                return Response({
                    'success': False,
                    'error': f"Unexpected error: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SyncMCMInvitationStatusView(APIView):
    """
    POST /api/gam/mcm-invitations/sync-status/ - Sync all invitation statuses
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            result = MCMService.sync_invitation_statuses()
            
            return Response({
                'success': True,
                'message': f"Synced {result['updated_count']} invitations",
                'updated_count': result['updated_count']
            })
            
        except Exception as e:
            logger.error(f"Error syncing invitation statuses: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManualMCMEntryView(APIView):
    """
    POST /api/gam/mcm-invitations/manual-entry/ - Add manual MCM entry
    UPDATED: Always creates YAML file for manual entries
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = AddChildAccountSerializer(data=request.data)
        if serializer.is_valid():
            invitation = serializer.save(invited_by=request.user)
            
            # 🆕 CREATE YAML FILE FOR MANUAL ENTRIES
            yaml_created = create_child_yaml_file(invitation)
            
            return Response({
                "success": True,
                "message": "Child account added manually.",
                "invitation": MCMInvitationSerializer(invitation).data,
                "yaml_file_created": yaml_created  # 🆕 Include YAML creation status
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ============================================================================
# PARTNER ASSIGNMENT VIEWS (UNCHANGED)
# ============================================================================

class AssignPartnerToChildAccountView(APIView):
    """
    POST /api/gam/assign-partner/ - Assign partner to child account
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request):
        serializer = AssignPartnerToChildSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        partner = serializer.validated_data["partner"]
        invitation = serializer.validated_data["invitation"]

        try:
            existing_assignment = AssignedPartnerChildAccount.objects.filter(invitation=invitation).first()

            if existing_assignment:
                # If already assigned to same partner, do nothing
                if existing_assignment.partner == partner:
                    return Response({
                        "success": True,
                        "message": f"This child is already assigned to {partner.email}",
                        "reassigned": False
                    }, status=status.HTTP_200_OK)

                # Update the assignment
                existing_assignment.partner = partner
                existing_assignment.assigned_by = request.user
                existing_assignment.assigned_at = timezone.now()
                existing_assignment.save()

                return Response({
                    "success": True,
                    "message": f"Partner updated to {partner.email} for {invitation.child_network_code}",
                    "reassigned": True
                }, status=status.HTTP_200_OK)

            # Create new assignment
            AssignedPartnerChildAccount.objects.create(
                partner=partner,
                invitation=invitation,
                assigned_by=request.user
            )

            return Response({
                "success": True,
                "message": f"{partner.email} assigned to {invitation.child_network_code}",
                "partner_id": partner.id,
                "invitation_id": invitation.id,
                "reassigned": False
            }, status=status.HTTP_201_CREATED)

        except IntegrityError:
            return Response({
                "success": False,
                "error": "⚠️ Integrity error: duplicate or conflicting assignment."
            }, status=status.HTTP_400_BAD_REQUEST)


class GetAssignedAccountsForPartnerView(APIView):
    """
    GET /api/gam/partners/{partner_id}/assigned-accounts/ - Get assigned accounts
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, partner_id):
        assigned_links = AssignedPartnerChildAccount.objects.filter(
            partner_id=partner_id
        ).select_related('invitation')
        
        invitations = [assignment.invitation for assignment in assigned_links]
        
        serializer = MCMInvitationListSerializer(invitations, many=True)
        return Response(serializer.data)


# ============================================================================
# ADMIN VIEWS (UPDATED WITH YAML DELETION)
# ============================================================================

class AdminMCMInvitationListView(ListAPIView):
    """
    GET /api/gam/admin/mcm-invitations/ - Admin list of MCM invitations
    """
    permission_classes = [IsAdminUser]
    serializer_class = MCMInvitationListSerializer

    def get_queryset(self):
        return MCMInvitation.objects.select_related('parent_network', 'invited_by')


class UpdateInvitationUserStatusView(APIView):
    """
    PATCH /api/gam/mcm-invitations/{id}/toggle-status/ - Update user status
    
    Note: Partners can view but only admins can modify GAM status
    """
    permission_classes = [IsAuthenticated]
    
    def patch(self, request, pk):
        # Check if user can modify GAM status
        if not can_modify_gam_status(request.user):
            return Response({
                "error": "Permission denied",
                "detail": "Only administrators can modify GAM status"
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            invitation = MCMInvitation.objects.get(pk=pk)
        except MCMInvitation.DoesNotExist:
            return Response({"error": "Invitation not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = MCMInvitationUserStatusUpdateSerializer(
            invitation, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "id": invitation.id,
                "new_status": invitation.user_status,
                "message": f"User status updated to '{invitation.user_status}'"
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateChildAccountDetailsView(APIView):
    """
    PATCH /api/gam/mcm-invitations/{id}/update-details/ - Update child account
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def patch(self, request, pk):
        try:
            invitation = MCMInvitation.objects.get(pk=pk)
        except MCMInvitation.DoesNotExist:
            return Response({"error": "Invitation not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = MCMInvitationUpdateSerializer(
            invitation, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "updated": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DeleteChildAccountView(APIView):
    """
    DELETE /api/gam/mcm-invitations/{id}/delete/ - Delete child account
    UPDATED: Deletes associated YAML file
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def delete(self, request, pk):
        try:
            invitation = MCMInvitation.objects.get(pk=pk)
        except MCMInvitation.DoesNotExist:
            return Response(
                {"error": "Child account not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # 🆕 GET CHILD NETWORK CODE BEFORE DELETION
        child_network_code = invitation.child_network_code
        
        # Delete the invitation
        invitation.delete()
        
        # 🆕 DELETE ASSOCIATED YAML FILE
        yaml_deleted = delete_child_yaml_file(child_network_code)
        
        return Response({
            "success": True, 
            "message": "Child account and related data deleted.",
            "yaml_file_deleted": yaml_deleted  # 🆕 Include YAML deletion status
        })


class CheckGAMAPIAccessView(APIView):
    """
    POST /api/gam/mcm-invitations/{id}/check-gam-access/ - Check GAM API access for specific network
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        try:
            invitation = MCMInvitation.objects.get(pk=pk)
        except MCMInvitation.DoesNotExist:
            return Response(
                {"error": "Invitation not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # Import here to avoid circular imports
            from gam_accounts.services import GAMNetworkService
            
            # Test GAM API access for this specific network
            child_network_code = invitation.child_network_code
            
            try:
                # Try to get GAM client for this network
                client = GAMNetworkService.get_googleads_client(child_network_code)
                
                # Test with a simple API call (get network info)
                network_service = client.GetService("NetworkService", version="v202508")
                network = network_service.getCurrentNetwork()
                
                # If we get here, GAM API is accessible - UPDATE STATUS TO ACTIVE
                logger.info(f"✅ GAM API access successful for {child_network_code}")
                
                # Update invitation status to active since GAM API is working
                invitation.status = "accepted"
                invitation.save()
                
                # Get network display name safely
                network_name = ""
                try:
                    if hasattr(network, 'displayName'):
                        network_name = network.displayName
                    elif hasattr(network, 'networkName'):
                        network_name = network.networkName
                except:
                    network_name = f"Network {child_network_code}"
                
                return Response({
                    "success": True,
                    "gam_accessible": True,
                    "network_code": child_network_code,
                    "network_name": network_name,
                    "message": f"GAM API access successful for {child_network_code}. Status updated to active."
                })
                
            except Exception as e:
                # GAM API access failed - UPDATE STATUS TO INACTIVE
                logger.warning(f"❌ GAM API access failed for {child_network_code}: {str(e)}")
                
                # Update invitation status to indicate API access issues
                invitation.status = "api_error"
                invitation.save()
                
                return Response({
                    "success": True,
                    "gam_accessible": False,
                    "network_code": child_network_code,
                    "error": str(e),
                    "message": f"GAM API access failed for {child_network_code}. Status updated to inactive."
                })
                
        except Exception as e:
            logger.error(f"❌ Error checking GAM access for {invitation.child_network_code}: {str(e)}")
            return Response({
                "success": False,
                "error": f"Failed to check GAM access: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ToggleServiceKeyStatusView(APIView):
    """
    PATCH /api/gam/mcm-invitations/{id}/toggle-service-key/ - Toggle service key status
    """
    permission_classes = [IsAuthenticated]
    
    def patch(self, request, pk):
        try:
            invitation = MCMInvitation.objects.get(pk=pk)
        except MCMInvitation.DoesNotExist:
            return Response(
                {"error": "Invitation not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # Get the new status from request data
            new_status = request.data.get('service_account_enabled')
            if new_status is None:
                return Response(
                    {"error": "service_account_enabled field is required"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update the service account status
            invitation.service_account_enabled = new_status
            invitation.save()
            
            logger.info(f"✅ Service key status updated for {invitation.child_network_code}: {new_status}")
            
            return Response({
                "success": True,
                "child_network_code": invitation.child_network_code,
                "service_account_enabled": invitation.service_account_enabled,
                "message": f"Service key status updated to {'active' if new_status else 'inactive'}"
            })
            
        except Exception as e:
            logger.error(f"❌ Error updating service key status for {invitation.child_network_code}: {str(e)}")
            return Response({
                "success": False,
                "error": f"Failed to update service key status: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# UPDATED VIEW SUMMARY
# ============================================================================

"""
🎯 YAML FILE MANAGEMENT CHANGES

✅ NEW HELPER FUNCTIONS:
├── create_child_yaml_file(invitation)     → Creates YAML for child networks
└── delete_child_yaml_file(network_code)   → Removes YAML files

✅ UPDATED VIEWS:
├── SendMCMInvitationView                   → Creates YAML when real_invitation_sent=True
├── ManualMCMEntryView                      → Always creates YAML for manual entries
└── DeleteChildAccountView                  → Deletes YAML file when invitation deleted

✅ YAML FILE STRUCTURE:
ad_manager:
  application_name: 'GAM Management Platform'
  network_code: {child_network_code}        # From invitation.child_network_code
  path_to_private_key_file: 'key.json'
  delegated_account: 'report@hnt-gaming.iam.gserviceaccount.com'

✅ NAMING: {child_network_code}.yaml (e.g., "12345678.yaml")

✅ RESPONSE UPDATES:
- SendMCMInvitationView: Added 'yaml_file_created' field
- ManualMCMEntryView: Added 'yaml_file_created' field  
- DeleteChildAccountView: Added 'yaml_file_deleted' field
"""

# ============================================================================
# PARENT GAM USER CREATION
# ============================================================================

class CreateParentGAMUserView(APIView):
    """
    POST /api/gam/create-parent-user/
    Create a parent GAM user with minimal required fields
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request):
        serializer = ParentGAMUserCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = serializer.save()
                return Response({
                    'message': 'Parent GAM user created successfully',
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'username': user.username,
                        'role': user.role,
                        'company_name': user.company_name,
                        'status': user.status
                    }
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"Error creating parent GAM user: {str(e)}")
                return Response({
                    'error': 'Failed to create parent GAM user',
                    'details': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DashboardStatsView(APIView):
    """
    GET /api/gam/dashboard-stats/ - Get dashboard statistics
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get total accounts and approved accounts
            total_accounts = MCMInvitation.objects.count()
            approved_accounts = MCMInvitation.objects.filter(
                status__in=['accepted', 'approved']
            ).count()
            
            # Get partner statistics
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            total_partners = User.objects.filter(role='partner').count()
            
            # Get new partners in last 30 days
            from datetime import datetime, timedelta
            thirty_days_ago = datetime.now() - timedelta(days=30)
            new_partners = User.objects.filter(
                role='partner',
                date_joined__gte=thirty_days_ago
            ).count()
            
            # Get open tickets count
            try:
                from tickets.models import Ticket
                open_tickets = Ticket.objects.filter(
                    status__in=['open', 'in_progress']
                ).count()
            except ImportError:
                open_tickets = 0
            
            return Response({
                'accounts': {
                    'total': total_accounts,
                    'approved': approved_accounts,
                    'approval_rate': round((approved_accounts / total_accounts * 100), 1) if total_accounts > 0 else 0
                },
                'partners': {
                    'total': total_partners,
                    'new_last_30_days': new_partners
                },
                'tickets': {
                    'open': open_tickets
                }
            })
            
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {str(e)}")
            return Response({
                'error': 'Failed to fetch dashboard statistics'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)