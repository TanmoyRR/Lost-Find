import os
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


ALLOWED_IMAGE_TYPES = {
    'image/jpeg': ('jpg', 'jpeg'),
    'image/png': ('png',),
    'image/gif': ('gif',),
    'image/webp': ('webp',),
}

ALLOWED_IMAGE_EXTENSIONS = {ext for exts in ALLOWED_IMAGE_TYPES.values() for ext in exts}

# 5MB default limit
DEFAULT_MAX_UPLOAD_SIZE = 5 * 1024 * 1024

# Profile-specific limits
PROFILE_MAX_UPLOAD_SIZE = 3 * 1024 * 1024


@deconstructible
class FileUploadValidator:
    """Reusable file upload validator that checks size, extension, and MIME type."""

    def __init__(self, max_size=DEFAULT_MAX_UPLOAD_SIZE, allowed_types=None, allowed_extensions=None):
        self.max_size = max_size
        self.allowed_types = allowed_types or ALLOWED_IMAGE_TYPES
        self.allowed_extensions = allowed_extensions or ALLOWED_IMAGE_EXTENSIONS

    def __call__(self, value):
        if value is None:
            return

        # Check file size
        if hasattr(value, 'size') and value.size > self.max_size:
            max_mb = self.max_size / (1024 * 1024)
            raise ValidationError(f'File too large. Maximum size is {max_mb:.0f}MB.')

        # Check file extension
        ext = os.path.splitext(value.name)[1].lower().lstrip('.')
        if ext not in self.allowed_extensions:
            raise ValidationError(
                f'Unsupported file type. Allowed types: {", ".join(sorted(self.allowed_extensions))}.'
            )

        # Validate actual image content using PIL
        try:
            from PIL import Image
            value.seek(0)
            img = Image.open(value)
            img.verify()
            value.seek(0)

            # Re-open after verify (verify closes the file)
            img = Image.open(value)
            if img.format and img.format.lower() not in {t.split('/')[-1].lower() for t in self.allowed_types}:
                raise ValidationError(
                    f'Unsupported image format. Allowed formats: {", ".join(sorted(self.allowed_extensions))}.'
                )
            value.seek(0)
        except ValidationError:
            raise
        except Exception:
            raise ValidationError('Invalid or corrupted image file.')

    def __eq__(self, other):
        return (
            isinstance(other, FileUploadValidator) and
            self.max_size == other.max_size and
            self.allowed_types == other.allowed_types
        )


def validate_post_image(value):
    """Validate post image uploads (5MB, images only)."""
    validator = FileUploadValidator(max_size=DEFAULT_MAX_UPLOAD_SIZE)
    validator(value)


def validate_profile_image(value):
    """Validate profile image uploads (3MB, images only)."""
    validator = FileUploadValidator(max_size=PROFILE_MAX_UPLOAD_SIZE)
    validator(value)
