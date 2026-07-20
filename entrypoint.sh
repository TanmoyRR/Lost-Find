#!/bin/bash
set -e

echo "Running entrypoint.sh..."

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Seed initial data (safe to run multiple times)
echo "Seeding initial data..."
python manage.py seed_data

# Create superuser if not exists (optional - uncomment if needed)
# echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.get_or_create(username='admin', defaults={'email':'admin@iubat.edu', 'role':'admin', 'is_superuser':True, 'is_staff':True})" | python manage.py shell

echo "Starting Gunicorn..."
exec gunicorn core.wsgi:application --workers 4 --bind 0.0.0.0:8000 --timeout 120
