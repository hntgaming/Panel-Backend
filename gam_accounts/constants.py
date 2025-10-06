"""
GAM API Version Constants
Based on Google Ad Manager API deprecation schedule
"""

# Current API version (latest available)
GAM_API_VERSION = 'v202505'

# API version history with deprecation dates
GAM_API_VERSIONS = {
    'v202505': {
        'status': 'current',
        'deprecation_date': '2026-02-01',
        'sunset_date': '2026-05-01',
        'description': 'Latest stable version'
    },
    'v202502': {
        'status': 'active',
        'deprecation_date': '2025-11-01', 
        'sunset_date': '2026-02-01',
        'description': 'Previous version'
    }
}

def get_current_api_version():
    """Get the current API version"""
    return GAM_API_VERSION

def get_service(client, service_name, version=None):
    """
    Get a GAM service with proper version
    """
    if version is None:
        version = GAM_API_VERSION
        
    return client.GetService(service_name, version=version)