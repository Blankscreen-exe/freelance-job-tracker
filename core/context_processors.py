from django.conf import settings


def app_globals(request):
    from core.models import AppSettings
    try:
        branding = AppSettings.get()
    except Exception:
        # DB not ready (migrations pending)
        return {'APP_NAME': getattr(settings, 'APP_NAME', 'Job Tracker'), 'BRANDING': None}

    return {
        'APP_NAME': branding.app_name,
        'BRANDING': branding,
    }
