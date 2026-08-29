#!/bin/bash
set -e

echo "Running entrypoint.sh..."

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Seed initial data (safe to run multiple times, skip admin in production)
echo "Seeding initial data..."
python manage.py seed_data --production

echo "Starting Gunicorn..."
exec gunicorn core.wsgi:application --workers 4 --bind 0.0.0.0:8000 --timeout 120
