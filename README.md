# IUBAT Lost & Found Management System with AI Features

A production-ready Django web application for managing lost and found items at IUBAT University, featuring AI-powered semantic search and automatic matching.

## Features

- **Lost & Found Posting**: Create, edit, and manage lost/found posts with images
- **AI Semantic Search**: Natural language search (e.g., "lost samsung phone" finds "found android mobile")
- **Automatic AI Matching**: Auto-match lost with found items using sentence-transformers
- **Membership System**: Annual membership (100 BDT) via SSLCommerz
- **User Roles**: Guest, Student/User, Admin with full RBAC
- **Custom Admin Dashboard**: Full admin panel (no Django admin UI)
- **User Dashboard**: Modern dashboard with stats, activity, AI matches

## Tech Stack

- **Backend**: Django 5.0, Gunicorn
- **Frontend**: Tailwind CSS, Alpine.js, Bootstrap Icons
- **Database**: PostgreSQL 15+
- **AI**: sentence-transformers (all-MiniLM-L6-v2) + cosine similarity
- **Payment**: SSLCommerz
- **Task Queue**: Celery + Redis (optional)
- **Proxy**: Nginx
- **Deployment**: Docker, Heroku, or bare-metal

---

## Quick Start (Development)

```bash
# 1. Clone
git clone <repo-url> && cd LostFind

# 2. Virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your database credentials

# 5. Create database
createdb iubat_lostfind

# 6. Run migrations & seed
python manage.py migrate
python manage.py seed_data
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
git clone <your-repo-url> /var/www/lostfind
cd /var/www/lostfind

# 4. Set up Python environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Configure PostgreSQL
sudo -u postgres psql -c "CREATE DATABASE iubat_lostfind;"
sudo -u postgres psql -c "CREATE USER lostfind_user WITH PASSWORD 'your_strong_password';"
sudo -u postgres psql -c "ALTER ROLE lostfind_user SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE lostfind_user SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE lostfind_user SET timezone TO 'Asia/Dhaka';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE iubat_lostfind TO lostfind_user;"

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
git clone <repo-url> && cd LostFind
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
git clone <repo-url> /var/www/lostfind
cd /var/www/lostfind

# 3. Python setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Database
sudo -u postgres psql -c "CREATE DATABASE iubat_lostfind;"
sudo -u postgres psql -c "CREATE USER lostfind_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "ALTER ROLE lostfind_user SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE lostfind_user SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE lostfind_user SET timezone TO 'Asia/Dhaka';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE iubat_lostfind TO lostfind_user;"

# 5. Environment
cp .env.example .env
nano .env   # Set DB credentials, SECRET_KEY, etc.

# 6. Migrate & seed
python manage.py migrate
python manage.py seed_data
python manage.py collectstatic --noinput
python manage.py createsuperuser

# 7. Gunicorn systemd service
sudo nano /etc/systemd/system/lostfind.service
```

Create the systemd service file:

```ini
[Unit]
Description=IUBAT Lost & Find Gunicorn Service
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/lostfind
ExecStart=/var/www/lostfind/venv/bin/gunicorn core.wsgi:application --workers 4 --bind unix:/var/www/lostfind/lostfind.sock --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable lostfind
sudo systemctl start lostfind

# 8. Nginx configuration
sudo nano /etc/nginx/sites-available/lostfind
```

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    client_max_body_size 100M;

    location /static/ {
        alias /var/www/lostfind/staticfiles/;
    }

    location /media/ {
        alias /var/www/lostfind/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/lostfind/lostfind.sock;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/lostfind /etc/nginx/sites-enabled
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
# Add Postgres plugin
# Set environment variables in Railway dashboard
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
| `DB_NAME` | **Yes** | iubat_lostfind | PostgreSQL database name |
| `DB_USER` | **Yes** | postgres | PostgreSQL user |
| `DB_PASSWORD` | **Yes** | - | PostgreSQL password |
| `DB_HOST` | **Yes** | localhost | PostgreSQL host |
| `DB_PORT` | No | 5432 | PostgreSQL port |
| `SSLCOMMERZ_STORE_ID` | **Yes** | - | SSLCommerz store ID |
| `SSLCOMMERZ_STORE_PASS` | **Yes** | - | SSLCommerz store password |
| `SSLCOMMERZ_IS_SANDBOX` | No | True | Use sandbox mode |
| `EMAIL_HOST_USER` | **Yes** | - | SMTP email |
| `EMAIL_HOST_PASSWORD` | **Yes** | - | SMTP password |
| `SITE_URL` | **Yes** | - | Your production URL |

## Project Structure

```
LostFind/
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

**AI model not working**
- The first load downloads the model (~90MB). Ensure internet connectivity.
- If memory is limited, the AI features degrade gracefully (return empty results).
