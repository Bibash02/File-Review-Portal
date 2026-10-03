"""
Pluggable virus scanning. Set settings.FILE_SCANNER to a dotted path.

In production don't scan inline: save with scan_status=pending, then run
`scan_version` from a Celery task via transaction.on_commit(...).
"""
import logging

from django.conf import settings
from django.utils.module_loading import import_string

from .models import DocumentVersion

log = logging.getLogger(__name__)
S = DocumentVersion.ScanStatus

class NoopScanner:
    def scan(self, fileobj):
        return S.SKIPPED

class ClamAVScanner:
    def scan(self, fileobj):
        import clamd 

        cd = clamd.ClamdNetworkSocket(host=settings.CLAMAV_HOST, port=settings.CLAMAV_PORT)
        status, _sig = cd.instream(fileobj)["stream"]
        return S.INFECTED if status == "FOUND" else S.CLEAN

def scan_version(version):
    scanner = import_string(settings.FILE_SCANNER)()
    try:
        with version.file.storage.open(version.file.name, "rb") as fh:
            version.scan_status = scanner.scan(fh)
    except Exception:  # scanner down -> stay "pending" (quarantined if REQUIRE_CLEAN_SCAN)
        log.exception("Scan failed for version %s", version.pk)
        version.scan_status = S.PENDING
    version.save(update_fields=["scan_status"])
    return version.scan_status
