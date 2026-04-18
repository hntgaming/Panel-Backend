"""
Main URL configuration with clean separation between API and Admin
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods


def api_root(request):
    """
    API root endpoint - provides API information
    """
    from django.conf import settings as django_settings
    return JsonResponse({
        'message': 'Welcome to H&T GAMING - Managed Inventory API',
        'version': '2.0',
        'endpoints': {
            'authentication': '/api/auth/',
            'reports': '/api/reports/',
            'admin_panel': '/admin/',
            'api_docs': '/api/docs/' if django_settings.DEBUG else None,
        },
        'auth_info': {
            'type': 'JWT Bearer Token',
            'header': 'Authorization: Bearer <token>',
            'login_endpoint': '/api/auth/login/',
        }
    })


@ensure_csrf_cookie
@require_http_methods(["GET"])
def csrf_token_view(request):
    """
    Endpoint to get CSRF token for admin interface
    Only needed for Django admin, not for API
    """
    from django.middleware.csrf import get_token
    return JsonResponse({
        'csrf_token': get_token(request),
        'note': 'This token is only needed for Django admin interface, not for API endpoints'
    })


urlpatterns = [
    # Django Admin (uses CSRF + sessions)
    path('admin/', admin.site.urls),
    
    # CSRF token endpoint (for admin interface only)
    path('api/csrf/', csrf_token_view, name='csrf_token'),
    
    # API Root
    path('api/', api_root, name='api_root'),
    
    # API Authentication (JWT-based, no CSRF needed)
    path('api/auth/', include('accounts.urls')),
    
    # GAM Accounts API removed - simplified for managed inventory
    
    # Reports API
    path('api/reports/', include('reports.urls')),
]

# Development URLs
from django.conf import settings
if settings.DEBUG:
    from django.conf.urls.static import static
    from django.urls import re_path
    from django.views.generic import TemplateView
    
    # Serve media files in development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # API documentation placeholder
    urlpatterns += [
        path('api/docs/', TemplateView.as_view(
            template_name='api_docs.html',
            extra_context={'title': 'GAM Platform API Documentation'}
        ), name='api_docs'),
    ]