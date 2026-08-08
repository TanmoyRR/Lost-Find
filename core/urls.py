from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.accounts.urls', namespace='accounts')),
    path('', include('apps.posts.urls', namespace='posts')),
    path('membership/', include('apps.membership.urls', namespace='membership')),
    path('payments/', include('apps.payments.urls', namespace='payments')),
    path('ai/', include('apps.ai_engine.urls', namespace='ai')),
    path('notifications/', include('apps.notifications.urls', namespace='notifications')),
    path('', include('apps.pages.urls', namespace='pages')),
    path('', include('apps.accounts.dashboard_urls', namespace='dashboard')),
    path('recovery/', include('apps.recovery.urls', namespace='recovery')),
    path('messages/', include('apps.messaging.urls', namespace='messaging')),
]

if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
