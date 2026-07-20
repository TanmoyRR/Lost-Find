import os
import compat_patch  # Python 3.14 compatibility fix
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
application = get_wsgi_application()
