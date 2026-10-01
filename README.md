# File Review Portal (Django + DRF)

Clients upload documents → reviewers comment / approve / reject → users download **approved** versions.

## Run

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py test                # 18 tests
python manage.py runserver
```

Create users in `/admin/` (set `role` = reviewer for reviewers). Get a token:

```bash
curl -X POST localhost:8000/api/auth/token/ -d "username=alice&password=..."
# -> {"token": "abc..."}   then: -H "Authorization: Token abc..."
```

## API

| Method | URL | Who |
|---|---|---|
| POST | `/api/documents/` (multipart: `title`, `file`) | any user → becomes owner, creates v1 |
| GET | `/api/documents/` , `/api/documents/{id}/` | owner / grantees / admin |
| DELETE | `/api/documents/{id}/` | owner (soft delete) |
| GET / POST | `/api/documents/{id}/versions/` | GET: see rules below · POST (multipart `file`): owner only |
| GET | `.../versions/{vid}/download/` | see rules below |
| POST | `.../versions/{vid}/download-link/` | same rules → 60s signed URL |
| GET | `/api/downloads/{token}/` | signed link (re-checks permission on redeem) |
| GET / POST | `.../versions/{vid}/comments/` | COMMENT level and up |
| POST | `.../versions/{vid}/review/` `{decision: approved\|rejected, comment}` | REVIEW level, not the owner |
| GET / POST | `/api/documents/{id}/access/` `{username, level}` | owner / admin |
| DELETE | `/api/documents/{id}/access/{username}/` | owner / admin |

### Permission model
| Level | Sees | Downloads |
|---|---|---|
| owner / admin | all versions | all versions |
| REVIEW (30, reviewer role only) | all versions + comments | all versions |
| COMMENT (20) | approved version + comments | approved only |
| VIEW (10) | approved version | approved only |
| no grant | 404 (existence not leaked) | – |

A new upload doesn't replace the approved version. The old approved one stays live until the new one is approved.

## Security checklist implemented
- **Size limit**: `UPLOAD_MAX_BYTES` (validator + early `Content-Length` check → 413). Also set `client_max_body_size` on nginx.
- **Type validation**: extension allowlist + magic-byte sniffing (+ zip structure for .docx). Client `Content-Type` ignored.
- **Filenames are input**: stored under `documents/<doc>/v<n>/<uuid>.<ext>`; display name sanitized.
- **Private storage**: `PRIVATE_MEDIA_ROOT`, no URL, never served statically; admin can't expose files either.
- **Downloads**: authorized views, `attachment`, `nosniff`, `no-store`; signed links are short-lived and re-authorized.
- **Scanning**: `FILE_SCANNER` hook (Noop / ClamAV). `REQUIRE_CLEAN_SCAN=1` quarantines until clean; infected is always blocked.
- **Cleanup**: soft deletes + `python manage.py cleanup_files [--dry-run] [--orphans]` (cron it).

## Going to production
- Swap `PrivateStorage` for S3/GCS private bucket (see `documents/storage.py`) and return presigned URLs.
- Run scans async (Celery + `transaction.on_commit`) and leave `REQUIRE_CLEAN_SCAN=1`.
- Postgres via `POSTGRES_*` env vars, real `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`.
