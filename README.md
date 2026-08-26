# IUBAT SmartFind: AI-Powered Lost & Found System

A production-ready Django web application for managing lost and found items at IUBAT University, featuring AI-powered smart search (Jina API embeddings) and automatic matching (Supabase PostgreSQL + pgvector).

## Features

- **Lost & Found Posting**: Create, edit, and manage lost/found posts with images
- **Smart Search (AI Semantic Search)**: Natural language search (e.g., "lost samsung phone" finds "found android mobile") via the Jina Embeddings API
- **Automatic AI Matching**: Auto-match lost with found items using pgvector cosine search + hybrid scoring; keyword search always works as fallback
- **Membership System**: Annual membership (100 BDT) via SSLCommerz
- **User Roles**: Guest, Student/User, Admin with full RBAC
- **Custom Admin Dashboard**: Full admin panel (no Django admin UI)
- **User Dashboard**: Modern dashboard with stats, activity, AI matches

## Tech Stack

- **Backend**: Django 5.0, Gunicorn
- **Frontend**: Tailwind CSS, Alpine.js, Bootstrap Icons
- **Database**: Supabase PostgreSQL 15+ with the pgvector extension
- **AI**: Jina Embeddings API (jina-embeddings-v5-text-nano) - no local model, no GPU
- **Payment**: SSLCommerz
- **Task Queue**: Celery + Redis (optional)
- **Proxy**: Nginx
- **Deployment**: Docker, Heroku, Railway, or bare-metal

---

## Quick Start (Development)

```bash
# 1. Clone
git clone <repo-url> && cd SmartFind

# 2. Virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your database credentials

# 5. Run migrations, seed, and generate AI embeddings
python manage.py migrate
python manage.py seed_data
python manage.py generate_embeddings   # backfills embeddings via the Jina API
python manage.py createsuperuser

# 7. Run dev server
python manage.py runserver
```

## Deployment to External Server

### Option 1: Docker (Recommended)

```bash
# 1. Copy and edit environment
cp .env.example .env
nano .env   # Set DEBUG=False, DB credentials, SECRET_KEY, etc.

# 2. Build and run
docker compose up -d --build

# 3. Create superuser
docker compose exec web python manage.py createsuperuser

# 4. Your app is live at http://your-server-ip:80
```

### Option 2: Manual Deployment (Ubuntu/Debian)

```bash
# 1. SSH into your server
ssh user@your-server-ip

# 2. Install dependencies
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev postgresql postgresql-contrib nginx git

# 3. Clone the project
git clone <your-repo-url> /var/www/smartfind
cd /var/www/smartfind

# 4. Set up Python environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Configure PostgreSQL
sudo -u postgres psql -c "CREATE DATABASE iubat_smartfind;"
sudo -u postgres psql -c "CREATE USER smartfind_user WITH PASSWORD 'your_strong_password';"
sudo -u postgres psql -c "ALTER ROLE smartfind_user SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE smartfind_user SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE smartfind_user SET timezone TO 'Asia/Dhaka';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE iubat_smartfind TO smartfind_user;"

# 6. Environment
cp .env.example .env
nano .env   # Fill in DB credentials, SECRET_KEY, etc.

# 7. Collect static files
python manage.py collectstatic --noinput

# 8. Test
python manage.py runserver 0.0.0.0:8000

# 9. Production with Gunicorn + Nginx
gunicorn core.wsgi:application --workers 4 --bind 0.0.0.0:8000 --daemon
# Then set up Nginx reverse proxy (see nginx.conf)
```

## Deployment Options

### Option 1: Docker (Recommended)

```bash
# 1. Clone and configure
git clone <repo-url> && cd SmartFind
cp .env.example .env
nano .env   # Set your values

# 2. Build and run
docker compose up -d --build

# 3. Create superuser
docker compose exec web python manage.py createsuperuser

# 4. Your app is live at http://your-server-ip
```

### Option 2: Heroku

```bash
# Prerequisites: Heroku CLI, PostgreSQL addon

heroku create your-app-name
heroku addons:create heroku-postgresql:mini
heroku config:set SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
heroku config:set DEBUG=False
heroku config:set ALLOWED_HOSTS=your-app-name.herokuapp.com
heroku config:set CSRF_TRUSTED_ORIGINS=https://your-app-name.herokuapp.com
git push heroku main
heroku run python manage.py migrate
heroku run python manage.py seed_data
heroku run python manage.py createsuperuser
```

### Option 3: Manual Ubuntu Server

```bash
# 1. System dependencies
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev postgresql postgresql-contrib nginx git

# 2. Clone project
git clone <repo-url> /var/www/smartfind
cd /var/www/smartfind

# 3. Python setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Database
sudo -u postgres psql -c "CREATE DATABASE iubat_smartfind;"
sudo -u postgres psql -c "CREATE USER smartfind_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "ALTER ROLE smartfind_user SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE smartfind_user SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE smartfind_user SET timezone TO 'Asia/Dhaka';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE iubat_smartfind TO smartfind_user;"

# 5. Environment
cp .env.example .env
nano .env   # Set DB credentials, SECRET_KEY, etc.

# 6. Migrate & seed
python manage.py migrate
python manage.py seed_data
python manage.py collectstatic --noinput
python manage.py createsuperuser

# 7. Gunicorn systemd service
sudo nano /etc/systemd/system/smartfind.service
```

Create the systemd service file:

```ini
[Unit]
Description=IUBAT SmartFind Gunicorn Service
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/smartfind
ExecStart=/var/www/smartfind/venv/bin/gunicorn core.wsgi:application --workers 4 --bind unix:/var/www/smartfind/smartfind.sock --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable smartfind
sudo systemctl start smartfind

# 8. Nginx configuration
sudo nano /etc/nginx/sites-available/smartfind
```

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    client_max_body_size 100M;

    location /static/ {
        alias /var/www/smartfind/staticfiles/;
    }

    location /media/ {
        alias /var/www/smartfind/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/smartfind/smartfind.sock;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/smartfind /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx

# 9. SSL with Let's Encrypt
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

### Option 4: Platform-as-a-Service (PythonAnywhere, Railway, Render)

**Railway:**
```bash
# Connect GitHub repo to Railway
# Add Postgres plugin (or point DB_* vars at Supabase)
# Set environment variables in Railway dashboard:
#   SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS,
#   DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT,
#   JINA_API_KEY, JINA_EMBEDDING_MODEL, JINA_EMBEDDING_DIMENSIONS,
#   and Supabase S3 vars (if using Supabase storage)
# No AI model installation needed on Railway - embeddings use the Jina API
# Deploy - Railway auto-detects the Procfile
```

**Render:**
```bash
# Connect GitHub repo
# Set build command: pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput
# Set start command: gunicorn core.wsgi:application --workers 4 --bind 0.0.0.0:$PORT
# Add Postgres and Redis addons
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | **Yes** | - | Django secret key (generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DEBUG` | No | False | Set to True only in development |
| `ALLOWED_HOSTS` | **Yes** | localhost,127.0.0.1 | Comma-separated allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | **Yes** | - | Comma-separated trusted origins |
| `DB_NAME` | **Yes** | iubat_smartfind | PostgreSQL database name |
| `DB_USER` | **Yes** | postgres | PostgreSQL user |
| `DB_PASSWORD` | **Yes** | - | PostgreSQL password |
| `DB_HOST` | **Yes** | localhost | PostgreSQL host |
| `DB_PORT` | No | 5432 | PostgreSQL port |
| `JINA_API_KEY` | **Yes (for AI)** | - | Jina API key (backend only, never commit) |
| `JINA_EMBEDDING_MODEL` | No | jina-embeddings-v5-text-nano | Jina embedding model |
| `JINA_EMBEDDING_DIMENSIONS` | No | 256 | Vector dimension (must match the pgvector column) |
| `SSLCOMMERZ_STORE_ID` | **Yes** | - | SSLCommerz store ID |
| `SSLCOMMERZ_STORE_PASS` | **Yes** | - | SSLCommerz store password |
| `SSLCOMMERZ_IS_SANDBOX` | No | True | Use sandbox mode |
| `EMAIL_HOST_USER` | **Yes** | - | SMTP email |
| `EMAIL_HOST_PASSWORD` | **Yes** | - | SMTP password |
| `SITE_URL` | **Yes** | - | Your production URL |

## Project Structure

```
SmartFind/
├── core/                    # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py / asgi.py
│   └── celery.py
├── apps/
│   ├── accounts/            # Auth, profiles, dashboards
│   ├── posts/               # Lost/found posts
│   ├── membership/          # Membership plans
│   ├── payments/            # SSLCommerz integration
│   ├── ai_engine/           # AI search & matching
│   ├── notifications/       # Notifications
│   └── pages/               # Public pages
├── templates/               # All Django templates
├── static/                  # Static assets
├── media/                   # User uploads
├── Dockerfile               # Docker build
├── docker-compose.yml      # Docker orchestration
├── nginx.conf               # Nginx reverse proxy config
├── gunicorn.conf.py         # Gunicorn config
├── Procfile                 # Heroku / PaaS config
├── runtime.txt              # Python version for Heroku
├── entrypoint.sh            # Docker entrypoint
├── requirements.txt
└── .env.example
```

## Deployment Checklist

Before deploying to production:

- [ ] Set `DEBUG=False` in `.env`
- [ ] Generate a strong `SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- [ ] Set `ALLOWED_HOSTS` to your domain(s)
- [ ] Set `CSRF_TRUSTED_ORIGINS` to your domain(s)
- [ ] Use strong DB password
- [ ] Configure SSLCommerz with live credentials
- [ ] Set up SSL certificate (Let's Encrypt)
- [ ] Configure email (SMTP)
- [ ] Set `DEBUG=False` and remove `django-debug-toolbar` from requirements
- [ ] Set up regular database backups
- [ ] Configure logging
- [ ] Set up monitoring (optional)

## Troubleshooting

**"ModuleNotFoundError: No module named 'celery'"**
- Celery/Redis are optional. Comment them out in `requirements.txt` if you don't have Redis.

**"relation does not exist"**
- Run `python manage.py migrate` to create all database tables.

**"No module named 'debug_toolbar'"**
- This is a dev-only dependency. Either install it or set `DEBUG=False`.

**Static files not loading**
- Run `python manage.py collectstatic --noinput`
- Ensure `whitenoise` is in MIDDLEWARE (it is by default)

**AI features not returning results**
- Smart Search / AI Matching require: (1) `JINA_API_KEY` set, (2) a PostgreSQL database with pgvector, (3) post embeddings generated. Run `python manage.py generate_embeddings` after migrating. If the Jina API is down or the key is invalid, Smart Search automatically falls back to keyword search and post creation still works.
- On Supabase, pgvector may need enabling once: `CREATE EXTENSION IF NOT EXISTS vector;` (usually already enabled).
