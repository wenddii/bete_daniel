"""
URL configuration for Bete Daniel Hotel project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls', namespace='core')),
    path('rooms/', include('apps.rooms.urls', namespace='rooms')),
    path('reservations/', include('apps.reservations.urls', namespace='reservations')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
