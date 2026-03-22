from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import render


def home(request):
    if request.user.is_authenticated:
        from django.shortcuts import redirect
        return redirect('dashboard')
    return render(request, 'home.html')


def handler403(request, exception=None):
    return render(request, 'errors/403.html', status=403)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('home/', home, name='home'),
    path('', include('core.urls')),
]

# Serve media files in development (when not using S3)
if settings.DEBUG and not hasattr(settings, 'AWS_S3_ENDPOINT_URL'):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
