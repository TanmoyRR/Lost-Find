from django.conf import settings
from django.core.files.storage import Storage
from django.core.files.base import ContentFile
import os
from pathlib import Path


class SupabaseStorage(Storage):
    def __init__(self):
        self.bucket = settings.SUPABASE_BUCKET
        self.supabase_url = settings.SUPABASE_URL
        self.supabase_key = settings.SUPABASE_KEY

    def _open(self, name, mode='rb'):
        import requests
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{name}"
        headers = {"Authorization": f"Bearer {self.supabase_key}"}
        resp = requests.get(url, headers=headers)
        return ContentFile(resp.content)

    def _save(self, name, content):
        import requests
        import uuid
        ext = name.split('.')[-1] if '.' in name else ''
        filename = f"{uuid.uuid4()}.{ext}"
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{filename}"
        headers = {"Authorization": f"Bearer {self.supabase_key}"}
        files = {"file": (filename, content.read())}
        resp = requests.post(url, headers=headers, files=files)
        return filename

    def url(self, name):
        return f"{self.supabase_url}/storage/v1/object/public/{self.bucket}/{name}"

    def exists(self, name):
        return False
