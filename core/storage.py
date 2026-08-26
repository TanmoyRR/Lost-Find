from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class SupabasePublicStorage(S3Boto3Storage):
    """S3-compatible storage for Supabase that serves files via the public
    REST URL. Supabase's S3 gateway does not allow anonymous reads, so the
    S3-style URL is rewritten to /storage/v1/object/public/<bucket>/<key>."""

    def url(self, name, parameters=None, expire=None):
        url = super().url(name, parameters=parameters, expire=expire)
        endpoint = settings.AWS_S3_ENDPOINT_URL
        if endpoint and url.startswith(endpoint):
            ref = endpoint.split('//')[1].split('.')[0]
            return f'https://{ref}.supabase.co/storage/v1/object/public/{self.bucket_name}/{name}'
        return url
