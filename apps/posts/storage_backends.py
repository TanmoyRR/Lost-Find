import logging
from django.conf import settings
from django.core.files.storage import Storage
from django.core.files.base import ContentFile
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class SupabaseStorage(Storage):
    def __init__(self):
        self.bucket = settings.SUPABASE_BUCKET
        self.supabase_url = settings.SUPABASE_URL
        self.supabase_key = settings.SUPABASE_KEY

    def _open(self, name, mode='rb'):
        import requests
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{name}"
        headers = {"Authorization": f"Bearer {self.supabase_key}"}
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return ContentFile(resp.content)
        except requests.RequestException as e:
            logger.error('SupabaseStorage._open failed for %s: %s', name, e)
            raise

    def _save(self, name, content):
        import requests
        import uuid
        ext = name.split('.')[-1] if '.' in name else ''
        filename = f"{uuid.uuid4()}.{ext}"
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{filename}"
        headers = {"Authorization": f"Bearer {self.supabase_key}"}
        files = {"file": (filename, content.read())}
        try:
            resp = requests.post(url, headers=headers, files=files, timeout=60)
            resp.raise_for_status()
            return filename
        except requests.RequestException as e:
            logger.error('SupabaseStorage._save failed for %s: %s', name, e)
            raise

    def url(self, name):
        return f"{self.supabase_url}/storage/v1/object/public/{self.bucket}/{name}"

    def exists(self, name):
        import requests
        url = f"{self.supabase_url}/storage/v1/object/info/{self.bucket}/{name}"
        headers = {"Authorization": f"Bearer {self.supabase_key}"}
        try:
            resp = requests.head(url, headers=headers, timeout=10)
            return resp.status_code == 200
        except requests.RequestException:
            return False
