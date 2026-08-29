web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py seed_data --production && daphne -b 0.0.0.0 -p $PORT core.asgi:application
release: python manage.py migrate --noinput
