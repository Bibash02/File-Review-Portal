import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """
    Local-disk storage that is NOT web-accessible: no public URL, ever.
    Files only leave through our authorized download views.

    PRODUCTION: swap for S3/GCS with a private ACL, e.g.

        from storages.backends.s3boto3 import S3Boto3Storage
        class PrivateStorage(S3Boto3Storage):
            default_acl = "private"
            querystring_auth = True        # presigned URLs
            querystring_expire = 60
            file_overwrite = False

    then redirect to `storage.url(name)` (presigned) instead of streaming.
    """

    # Read the setting lazily so tests / env overrides work.
    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Private files have no public URL. Use the download endpoints.")


def get_private_storage():
    return PrivateStorage()
