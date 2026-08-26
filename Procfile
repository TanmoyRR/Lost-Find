web: python manage.py collectstatic --noinput && gunicorn core.wsgi:application --workers 4 --bind 0.0.0.0:$PORT --timeout 120 --access-logfile -
release: python manage.py migrate --noinput
