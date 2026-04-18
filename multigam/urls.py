from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods


def api_root(request):
    return JsonResponse({'status': 'ok'})


def custom_404(request, exception):
    return JsonResponse({'error': 'not found'}, status=404)


def custom_500(request):
    return JsonResponse({'error': 'internal server error'}, status=500)


@ensure_csrf_cookie
@require_http_methods(["GET"])
def csrf_token_view(request):
    from django.middleware.csrf import get_token
    return JsonResponse({'token': get_token(request)})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/csrf/', csrf_token_view, name='csrf_token'),
    path('api/', api_root, name='api_root'),
    path('api/auth/', include('accounts.urls')),
    path('api/reports/', include('reports.urls')),
]

handler404 = custom_404
handler500 = custom_500

from django.conf import settings
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
