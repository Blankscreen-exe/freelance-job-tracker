from django.conf import settings


def app_globals(request):
    return {
        'APP_NAME': settings.APP_NAME,
    }
