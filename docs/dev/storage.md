# Storage and blobs

Study stores user data objects through the family object-storage contract.
The deployment backend is configuration, not a code path: **desktop is
always local**, web defaults to the mounted local volume,
and an AWS/Azure/cloud profile uses `s3` or `azure_blob` only.

Contract (vendored byte-identically from the family object-storage
contract):

- `backend/app/storage/object_storage.py`
- `backend/tests/fixtures/object_storage.fixtures.json`

Re-sync with the family contract sync tool; never edit the vendored copy.
The host's 200 MB upload ceiling is defined in `app/core/limits.py`; leave
the env cap unset to bind it.

## Shape

`BlobStore` (`app/storage/blobs.py`) is a thin wrapper over the contract's
`ObjectStore`:

| Method | Meaning |
|---|---|
| `put(data, mime=..., session=...)` | content-addressed, atomic write through the contract |
| `get(sha)` | bytes or `None` |
| `has(sha)` | existence check |
| `stream(sha)` | chunked iterator |
| `materialize(sha)` | private `0600` temp file (context manager), removed on exit |
| `path(sha)` | **local only**; raises `UnsupportedOperation` on a cloud backend |
| `delete(sha)` | remove the object (idempotent) |
| `known_shas(session)` | the `blobs` table index |

`BlobStore(Path(...))` keeps the legacy desktop/test construction and builds a
local store. `BlobStore(object_store)` wraps an already-built store.
`app.state.objects` is the contract store; `app.state.blobs` is the wrapper.

## Keys

The historical study layout is preserved — no desktop data migration:

```
<aa>/<bb>/<sha256>
```

`Blob.rel_path` keeps the same valid relative key. The contract's
`content_key()` (`sha256/aa/bb/<sha>`) is available for future layouts but is
not used by this host yet. Keys are server-generated; no user filename ever
becomes a path.

## Storage status card

Settings → Developer → **Storage** (admins only) is a read-only operator card,
not a provider wizard. It shows the resolved backend, bucket/container, key
prefix, region and endpoint host, SSE mode, per-object cap, presign TTL and the
live health row. There is deliberately no credential field, provider tile or
backend switch: storage is deployment configuration, and a switch is
`migrate_objects.py`, not a save button.

- API: `GET /api/v1/admin/storage/status` (admin-only; non-admins get 403).
  It reuses the cached, bounded `StorageHealthProbe` behind `/api/v1/health`.
- `?refresh=true` drops the 30 s health cache first, so the card's **Test
  connection** action performs a real probe instead of repeating a snapshot.
- The response carries no credentials, connection strings, presigned URLs or
  full endpoint URL — only the endpoint host.
- Desktop renders nothing (`local` is invisible); the section is filtered from
  the nav and unreachable through `?tab=developer&section=storage` for
  non-admins, the same rule as the Users tab.
- The family `app.storage` settings-map domain (scope `instance (admin)`,
  secrets `none`) is declared in `contracts/settings-map.json`; the frontend
  conformance test pins this host's developer sections to that declaration.

<!-- BEGIN family-object-storage (generated; edit the family canonical) -->

## Configuration

All variables are prefixed `SA_`; nothing unprefixed is read. `.env` and
the process environment both populate the host settings, and the storage
bootstrap maps the resolved values into the contract — application code
never reads the raw environment.

| Variable | Values | Default |
|---|---|---|
| `SA_CLOUD_PROFILE` | `aws` / `azure` / `gcp` / `cloud` / empty / `none` / `local` / `self_hosted` | empty (the last three mean "no profile") |
| `SA_OBJECT_STORAGE_BACKEND` | `local` / `s3` / `azure_blob` | profile default, else `local` |
| `SA_OBJECT_STORAGE_REQUIRED` | bool | `true` with a cloud profile |
| `SA_OBJECT_STORAGE_LOCAL_ROOT` | path | host data directory |
| `SA_OBJECT_STORAGE_MAX_MB` | 1–1024 | `200` (host ceiling) |
| `SA_OBJECT_STORAGE_PRESIGN_TTL` | 60–3600 | 300 |
| `SA_S3_BUCKET` / `_REGION` / `_ENDPOINT_URL` | provider config | — / SDK default / AWS |
| `SA_S3_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` / `_SESSION_TOKEN` | static credentials (all or none) | SDK chain |
| `SA_S3_PATH_STYLE` / `_KMS_KEY_ID` / `_PREFIX` | provider config | path-style when an endpoint is set / AWS-managed key / empty |
| `SA_S3_SSE` | `AES256` / `aws:kms` / `none` | `AES256` for cloud/AWS; `none` for a custom endpoint outside a cloud profile |
| `SA_S3_VERIFY_TLS` / `_CONNECT_TIMEOUT` / `_READ_TIMEOUT` / `_MAX_ATTEMPTS` | transport | `true` / 5 / 30 / 3 |
| `SA_AZURE_STORAGE_CONTAINER` / `_CONNECTION_STRING` / `_ACCOUNT_URL` / `_ACCOUNT_NAME` | provider config | — |
| `SA_AZURE_STORAGE_CREDENTIAL` | account key, SAS, or `managed_identity` | SDK default |
| `SA_AZURE_STORAGE_PREFIX` | object key prefix | empty |
| `SA_AZURE_CONNECT_TIMEOUT` / `_READ_TIMEOUT` / `_MAX_ATTEMPTS` | transport | 5 / 30 / 3 |

Resolution law:

- **Desktop is always local.** A desktop entrypoint with a cloud profile,
  `s3` or `azure_blob` is a boot error: there is no bucket, SDK or storage
  configuration on the desktop.
- **Cloud never runs local.** A server entrypoint with `aws`, `azure`,
  `gcp` or `cloud` never resolves to `local`; requesting `local` under any
  cloud profile is a boot error.
- **Server defaults to local.** With no profile and no requested backend,
  a server boots on the mounted local volume. `s3` / `azure_blob` is
  selected explicitly; an `azure` profile may select `s3` for an
  S3-compatible gateway.
- **Required forbids local.** `SA_OBJECT_STORAGE_REQUIRED=true` rejects
  `local` even without a cloud profile, and a cloud profile implies
  required.

The app builds and health-probes the store before it starts serving.
`probe=True` performs a cheap write/unlink under a local root,
`HeadBucket` for S3 and container properties for Azure, so a bad bucket,
container, credential or non-TLS cloud endpoint fails boot instead of the
first upload. The only sanctioned `probe=False` boot is the documented
read-only rollback window in the migration runbook.

**Upload ceiling.** Leave `SA_OBJECT_STORAGE_MAX_MB` unset unless the
deployment intentionally lowers the cap. `Study Assistant` binds unset to its
`200` MB host upload ceiling; the contract default is **100**
for hosts that do not bind one. Never pin 100 in compose to "match the
default" — an empty value is what binds the host ceiling.

## Transfer and security

**Uploads are server-mediated.** The host authenticates and authorizes
the caller, reads the body under `SA_OBJECT_STORAGE_MAX_MB`, validates
the content type and extension, sniffs the bytes, then calls
`store.put(key, data, content_type=..., metadata=...)` and persists the
key (never a path). The contract refuses presigned **PUT**: a browser
writing directly to the bucket bypasses authorization, the byte cap and
the audit trail. Do not add one later.

**Downloads have two legal shapes.** Use `store.stream(key)` through an
authenticated route (local, or a cloud backend where presigning is
unavailable), or `store.presign_get(key, ttl, download_filename=...,
inline=False)` which redirects to the provider for a short TTL.

- **GET-only presigning.** Presigned URLs are for reads; there is no
  presigned write.
- **TTL 60–3600 seconds.** The default is 300. Re-check authorization
  when the URL is minted; never log or store the URL.
- **`attachment` + `no-store` by default.** A presigned response carries
  `Content-Disposition: attachment` and `Cache-Control: no-store`.
- **Inline is an explicit image-only opt-in.** Set `inline=True` only for
  the image MIME types the host allows; never for HTML, SVG or XML.
- **`nosniff` always.** Streaming and redirected responses both carry
  `X-Content-Type-Options: nosniff`.
- **A vanished object is a 404.** A database row whose object is gone
  returns 404 when the stream opens; the ownership check still runs first.
- **Azure identity limits presigning.** A managed identity cannot sign a
  SAS; a SAS credential can access but not presign. In both cases the
  contract raises `UnsupportedOperation` and the host streams through the
  app instead of minting a broken URL.

## Cloud deployment checklist

Prerequisites:

- a **private, TLS-only** bucket or container: no public access, no
  plaintext HTTP endpoint;
- a **prefix per product and environment** (`SA_S3_PREFIX` /
  `SA_AZURE_STORAGE_PREFIX`, for example `prod/`), so one bucket can
  serve staging and production without collisions;
- a **least-privilege identity**: an instance/task role or managed
  identity over static keys, with list and object verbs only on the
  deployment prefix.

Deploy from the repository root with the production and cloud overlays:

```bash
docker compose -f docker/docker-compose.prod.yml \
               -f docker/docker-compose.cloud.yml up -d
```

**Success** means the app boots, its storage health probe passes, and an
upload followed by a download works end to end. **Failure** is a boot
error, not a degraded start: a missing bucket/container, missing or
one-sided static credentials, a non-HTTPS cloud endpoint or `SSE=none`
under a cloud profile stops the process.

- **Leave the max-MB cap unset.** An unset
  `SA_OBJECT_STORAGE_MAX_MB` binds to `Study Assistant`'s
  `200` MB host ceiling; the contract default is 100 for hosts
  that do not set one. Pin a lower value only intentionally.
- **The web image ships both extras.** Install `object-storage-s3` and
  `object-storage-azure` in the web image; desktop packaging installs
  neither. One image can therefore boot an S3 or Azure deployment.
- **An empty bucket/container is ready.** A newly provisioned, empty
  target needs no migration.
- **Existing data needs migration.** Pointing a cloud profile at an
  existing local volume without the `migrate-objects` tool serves empty
  objects. Follow the migration runbook below.
- **Do not mount the uploads volume** in a cloud deployment: the
  container is stateless for object bytes. Provider durability and
  versioning cover them; the database backup sidecar does not copy
  objects.

## Provider examples

**AWS S3 — instance/task role (recommended)**

Prerequisites: a private, TLS-only bucket in the chosen region. Grant the
instance/task role `s3:ListBucket` on the bucket and
`s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` on the deployment prefix.
With a customer-managed KMS key, also grant `kms:GenerateDataKey` and
`kms:Decrypt`.

```env
SA_CLOUD_PROFILE=aws
SA_OBJECT_STORAGE_BACKEND=s3
SA_S3_BUCKET=product-prod
SA_S3_REGION=eu-central-1
SA_S3_PREFIX=prod/
# SA_S3_SSE=aws:kms
# SA_S3_KMS_KEY_ID=arn:aws:kms:...
```

No static keys belong in env when the instance/task role supplies them.

**AWS S3 — static keys + KMS**

```env
SA_CLOUD_PROFILE=aws
SA_OBJECT_STORAGE_BACKEND=s3
SA_S3_BUCKET=product-prod
SA_S3_REGION=eu-central-1
SA_S3_ACCESS_KEY_ID=...
SA_S3_SECRET_ACCESS_KEY=...
SA_S3_SSE=aws:kms
SA_S3_KMS_KEY_ID=arn:aws:kms:...
SA_S3_PREFIX=prod/
```

Prefer the role over static keys; rotate them and never commit them.

**S3-compatible endpoint (MinIO/R2/B2/Wasabi/Ceph)**

Cloud profile — the contract requires SSE `AES256` or `aws:kms`:

```env
SA_CLOUD_PROFILE=cloud
SA_OBJECT_STORAGE_BACKEND=s3
SA_S3_BUCKET=product
SA_S3_ENDPOINT_URL=https://minio.example.com
SA_S3_PATH_STYLE=true
SA_S3_ACCESS_KEY_ID=...
SA_S3_SECRET_ACCESS_KEY=...
SA_S3_SSE=AES256
SA_S3_PREFIX=prod/
```

Gateway that rejects the AWS SSE header — run it as self-host object
storage instead of a cloud profile:

```env
SA_OBJECT_STORAGE_REQUIRED=true
SA_OBJECT_STORAGE_BACKEND=s3
SA_S3_BUCKET=product
SA_S3_ENDPOINT_URL=https://minio.example.com
SA_S3_PATH_STYLE=true
SA_S3_ACCESS_KEY_ID=...
SA_S3_SECRET_ACCESS_KEY=...
SA_S3_SSE=none
SA_S3_PREFIX=prod/
```

Outside a cloud profile, a custom endpoint defaults to `SSE=none`; many
S3-compatible gateways reject the AWS SSE header. Set `AES256` only when
the gateway supports it. A cloud profile always requires
`AES256`/`aws:kms`.

**Azure Blob — managed identity (recommended)**

Prerequisites: the container exists and is private/TLS-only. The identity
needs **Storage Blob Data Contributor** on the container (or account).
`azure-identity` is in the web image. This contract presigns only with an
account key; a managed identity therefore streams downloads through the
app.

```env
SA_CLOUD_PROFILE=azure
SA_OBJECT_STORAGE_BACKEND=azure_blob
SA_AZURE_STORAGE_CONTAINER=product-data
SA_AZURE_STORAGE_ACCOUNT_URL=https://product.blob.core.windows.net
SA_AZURE_STORAGE_ACCOUNT_NAME=product
SA_AZURE_STORAGE_CREDENTIAL=managed_identity
SA_AZURE_STORAGE_PREFIX=prod/
```

Do not put a raw expiring token in env; the `managed_identity` sentinel
selects `DefaultAzureCredential` (managed or workload identity).

**Azure Blob — connection string or account key**

Connection string:

```env
SA_CLOUD_PROFILE=azure
SA_OBJECT_STORAGE_BACKEND=azure_blob
SA_AZURE_STORAGE_CONTAINER=product-data
SA_AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=product;AccountKey=...;EndpointSuffix=core.windows.net
SA_AZURE_STORAGE_PREFIX=prod/
```

Account-key alternative (no connection string):

```env
SA_CLOUD_PROFILE=azure
SA_OBJECT_STORAGE_BACKEND=azure_blob
SA_AZURE_STORAGE_CONTAINER=product-data
SA_AZURE_STORAGE_ACCOUNT_URL=https://product.blob.core.windows.net
SA_AZURE_STORAGE_ACCOUNT_NAME=product
SA_AZURE_STORAGE_CREDENTIAL=<account-key>
SA_AZURE_STORAGE_PREFIX=prod/
```

A SAS token works for access but cannot presign (downloads stream); a
connection string or account key can presign. Account keys and SAS
tokens in env are secrets; prefer managed identity. Enable Azure soft
delete and versioning.

**Azure with an S3-compatible gateway (MinIO on Azure)**

```env
SA_CLOUD_PROFILE=azure
SA_OBJECT_STORAGE_BACKEND=s3
SA_S3_BUCKET=product
SA_S3_ENDPOINT_URL=https://minio.example.internal
SA_S3_ACCESS_KEY_ID=...
SA_S3_SECRET_ACCESS_KEY=...
SA_S3_PATH_STYLE=true
SA_S3_SSE=AES256
SA_S3_PREFIX=prod/
```

An explicit `s3` backend is allowed under the `azure` profile; use this
only when you actually run an S3 gateway. The azure cloud profile
requires SSE `AES256`/`aws:kms`; if the gateway rejects SSE, use the
self-host S3-compatible block above (no cloud profile,
`SA_OBJECT_STORAGE_REQUIRED=true`, `SSE=none`).

## Migration (local → object storage)

1. Provision the bucket/container, prefix and least-privilege identity.
2. **Keep the running app on `local`; run the migration process with the
   target backend.** The app service stays `SA_OBJECT_STORAGE_BACKEND=local`
   until the flip, but the one-shot migration command is started with
   `SA_OBJECT_STORAGE_BACKEND=s3` or `azure_blob` (and that process's
   bucket/container/prefix/credential variables). `migrate-objects
   --dry-run` prints the resolved backend and bucket/container and lists
   local files, keys, unreadable/missing files and collisions. It never
   stages bytes into a local root for later import: bytes go directly to the
   bucket/container the app will use.
3. **Quiesce writes** (maintenance window) or run dual-write. Copying while
   users upload can miss files that arrive after the enumeration.
4. Run `migrate-objects --apply` (idempotent, key-addressed, resumable
   through a migration manifest). It writes each object and verifies size
   and sha256. A manifest is bound to one host, source root and target
   (backend/bucket/prefix/endpoint); a different target is refused until
   the operator passes `--rebind`, which resets transferred entries to
   `pending` and requires a fresh `--apply`/`--verify`.
5. Re-run `--apply` until the delta is **zero**, then run
   `migrate-objects --verify`, which re-reads each object and compares the
   digest (and re-hashes any source that still exists). Any `missing`,
   `unreadable`, `collision` or `failed` entry is **blocking**: the command
   exits non-zero even when other objects verified. Only entries reported
   as `skipped` (no stable owner key, regenerable) are allowed.
6. Backfill the database **before** the flip: `migrate-objects
   --backfill-db` replaces absolute paths with keys and scrubs paths stored
   inside JSON. A dual-read helper (key first, then the legacy path under
   the mounted root) covers the transition. The legacy branch works only
   while the old volume is mounted. The command refuses to run unless
   `--verify` is clean.
7. Flip `SA_OBJECT_STORAGE_BACKEND` to `s3` or `azure_blob` and drop the
   migration-only overrides from the app service.
   - **Self-host:** keep the local root read-only for one release. A
     rollback release against that volume must boot with `probe=False`
     (the local health probe writes a `.health` file and would fail on a
     read-only mount).
   - **Cloud:** there is no legacy uploads volume, so the flip is final
     once `--verify` and the backfill are clean.
8. Remove the read-only volume after a clean release and a spot check.

An empty, newly provisioned bucket/container is ready to use without
migration; existing local data needs the `migrate-objects` tool. Never
rewrite objects in place.

**Memory and limits.** The contract's `put` takes bytes, so the tool reads
one whole object at a time. Keep every object under the configured
`SA_OBJECT_STORAGE_MAX_MB` / host ceiling; an entry over the cap fails
with a clear error instead of exhausting memory. On workers, budget temp
space and memory for one object per concurrent process.

<!-- END family-object-storage -->

## Migrate objects (runbook)

`backend/scripts/migrate_objects.py` copies the legacy content-addressed blob
tree into the configured store. Keys are preserved (`<aa>/<bb>/<sha256>`), so
verification compares the stored bytes with the sha256 in the key as well as
the manifest digest. There is no database backfill: the `blobs` table is keyed
by sha256, not by a path, and `--backfill-db` only reports that no-op.

The running **app service stays on `SA_OBJECT_STORAGE_BACKEND=local`**, but the
**migration process runs with the target backend** (`s3` or `azure_blob`) and
that process's `SA_S3_*`/`SA_AZURE_STORAGE_*` values. Run `--dry-run` first: it
prints the resolved backend and bucket/container. Never stage bytes into a
local root and then point the app at an empty bucket; copy directly to the
target the app will use.

```bash
cd backend

# 1. Plan: reports missing/unreadable blobs and key collisions; writes nothing.
python scripts/migrate_objects.py --dry-run

# 2. Copy, idempotent and resumable; the manifest is saved after every entry.
python scripts/migrate_objects.py --apply
python scripts/migrate_objects.py --apply      # re-run until the delta is zero

# 3. Re-read every target object and compare size + sha256. Every
#    missing/unreadable/collision/failed entry is blocking (exit 1).
python scripts/migrate_objects.py --verify

# 4. Flip the app's storage configuration (keep the old volume read-only for
#    one self-host release if a config rollback may be needed).

# 5. Optional, after a clean verify.
python scripts/migrate_objects.py --backfill-db   # no-op for study
```

The manifest defaults to
`<data_dir>/migrations/object-storage-manifest.json`; pass `--manifest PATH`
to keep it elsewhere. It records each source file (relative to `blobs_dir`),
its key, size, sha256, status, error and the **redacted target**
(backend, bucket/container, prefix, endpoint host — no credentials), plus the
host and source root. It is written atomically (directory fsync included), so
an interrupted run resumes. A different target, host or source root is refused;
`--rebind` adopts the current target and resets transferred entries to
`pending`, so they must be copied and verified again. A corrupt manifest aborts
the run; move it aside or `--force` starts a fresh ledger. `--force` is also
required when the target prefix already holds objects the manifest does not
own. Dry-run only warns about foreign objects; only apply refuses without
`--force`. The command refuses equal or nested source/target roots. `--verify`
requires a clean result before `--backfill-db`.

Rollback (self-host): flip `SA_OBJECT_STORAGE_BACKEND` back to `local` while
the old volume still exists; the rollback release boots with the local health
probe disabled (`probe=False`) if that volume is read-only. A cloud profile
has no legacy uploads volume, so its flip is final once `--verify` is clean.
The command never prints absolute source paths, reads one whole object per
`put` (keep each object under the configured cap), and **desktop never runs
it**: a desktop build is local-only and has no target.

## Deployment profiles (AWS / Azure)

The cloud overlay requires **both** the profile and the backend, so a
deployment cannot start on an empty interpolation default that silently
means `local`:

```bash
# AWS
SA_CLOUD_PROFILE=aws SA_OBJECT_STORAGE_BACKEND=s3 \
docker compose -f docker/docker-compose.prod.yml \
               -f docker/docker-compose.cloud.yml up -d

# Azure
SA_CLOUD_PROFILE=azure SA_OBJECT_STORAGE_BACKEND=azure_blob \
docker compose -f docker/docker-compose.prod.yml \
               -f docker/docker-compose.cloud.yml up -d
```

Put the provider values in `docker/.env` so both the app and the `backup`
sidecar interpolate the same backend. The overlay removes the uploads
volume; study still mounts `data` for `secrets.json`, cache and thumbnails.

**AWS.** Private, TLS-only bucket with Block Public Access on, versioning
on, and a `prod/` prefix (`SA_S3_PREFIX=prod/`). Prefer an instance/task
role over static keys; the role needs `s3:ListBucket` on the bucket (scoped
to the prefix with an `s3:prefix` condition) and
`s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` on
`arn:aws:s3:::<bucket>/<prefix>*`. A customer-managed KMS key
(`SA_S3_SSE=aws:kms`, `SA_S3_KMS_KEY_ID=…`) also needs
`kms:GenerateDataKey` and `kms:Decrypt`. Static keys
(`SA_S3_ACCESS_KEY_ID`/`SA_S3_SECRET_ACCESS_KEY`) use the same policy; rotate
them and never commit them. The default is SSE `AES256`; under a cloud
profile `SSE=none` is a boot error.

**Azure.** One private container with soft delete and versioning. Assign
the managed/workload identity **Storage Blob Data Contributor** on the
container scope and set
`SA_AZURE_STORAGE_CREDENTIAL=managed_identity` (no raw token in env). A
managed identity cannot presign, so downloads stream through the app. A
connection string (`SA_AZURE_STORAGE_CONNECTION_STRING`) or account key is
the fallback and can presign; treat both as secrets. Keep
`SA_AZURE_STORAGE_PREFIX=prod/` per environment.

## Boot health and observability

Boot builds and probes the store before serving: a missing bucket/container,
one-sided static credentials, a non-HTTPS cloud endpoint or `SSE=none`
raises a `StorageConfigError` and stops the process. The successful boot
logs one redacted line:

```
object storage: backend=s3 bucket/container=<bucket> prefix=prod sse=AES256
```

No access key, secret, session token or endpoint URL is logged.

`GET /api/v1/health` reports the storage row:

```json
{
  "status": "ok",
  "version": "0.9.0",
  "db": "ok",
  "storage": {"backend": "s3", "status": "ok", "required": true}
}
```

- The probe is cached for 30 s, so the compose healthcheck (every 30 s)
  does not hammer the provider.
- The provider call is bounded to about 5 s (a daemon thread + join), so a
  slow SDK timeout cannot outlive the container healthcheck; a timeout is
  reported like a transient provider error (degraded, or 503 when storage
  is required). Only contract errors and `OSError` count as storage state;
  an unexpected exception surfaces as a 500 instead of a fake outage.
- A transient provider failure **degrades open**: HTTP 200 with
  `status: degraded` and `storage.status: degraded`; this is not a restart.
- HTTP 503 (`status: unhealthy`, `storage.status: unavailable`) only when
  storage is required (a cloud profile or `SA_OBJECT_STORAGE_REQUIRED=true`)
  or the failure has been sustained for 300 s. A missing target is the boot
  error above, not a runtime 404.
- `detail` carries the contract error class name only — never a credential,
  bucket URL or presigned URL.

## Provider smoke (release gate)

Normal PRs run `local` only; the manual provider smoke is
`.github/workflows/cloud-smoke.yml` (`workflow_dispatch`, AWS and Azure
jobs). Repository configuration: `secrets.AWS_ACCESS_KEY_ID`,
`secrets.AWS_SECRET_ACCESS_KEY`, `vars.AWS_S3_TEST_BUCKET`,
`vars.AWS_S3_TEST_REGION`, `secrets.AZURE_STORAGE_CONNECTION_STRING`,
`vars.AZURE_STORAGE_TEST_CONTAINER`.

Run it locally with the same env-gated test module and a prefix inside the
IAM policy (`test/*`):

```bash
cd study-assistant
AWS_PROFILE=study-test SA_TEST_ALLOW_NETWORK=1 \
SA_TEST_S3_BUCKET=study-assistant-test SA_TEST_S3_REGION=eu-north-1 \
SA_TEST_S3_PREFIX=test/study-smoke \
uv run --directory backend --with boto3 pytest -q tests/test_object_storage_s3.py

SA_TEST_ALLOW_NETWORK=1 SA_TEST_AZURE_CONTAINER=study-data-tst-01 \
SA_TEST_AZURE_CONNECTION_STRING="$(your dotenv reader)" \
SA_TEST_AZURE_PREFIX=test/study-smoke \
uv run --directory backend --with azure-storage-blob \
  pytest -q tests/test_object_storage_azure.py
```

Never print or commit the connection string. The smoke must pass both
`run_conformance(store)` and the course export/import/duplicate round-trip.

## Family gates

The vendored contract, its fixture table and this page's generated block are
checked by the family adoption gate with `--check --strict`: a local edit to
a vendored copy, a stale generated block or a missing host fails alignment.
Adoption is complete, so none of the three hosts reports "pending" any more.

## Processors

Path-taking processors use `BlobStore.materialize(sha)` (or
`stream`/`get` when bytes are accepted). The temp file is `0600` and removed
on every exit path. Never pass a durable host path to a job; jobs keep
carrying `blob_sha` and the job process resolves it through the store.

Current seams:

| Layer | Store use |
|---|---|
| source ingest (`services/content/sources.py`) | `put(...)` for scanned/imported files |
| course export/import/duplicate | `has`/`get`/`put` through `BlobStore` |
| materials, capture, notes, lectures | existing `put/get`; audio purge uses `delete` |
| `/api/v1/blobs/{sha}` | owner-scoped `stream` (no `Path.read_bytes`) |
| scan scheduler | holds the store, passes it to `SourcesService` |

Local source-folder scanning (linked folders, vaults, the import inbox) is a
**desktop/self-host** feature: it reads a real filesystem path on the machine
running the app. Under an `s3`/`azure_blob` backend there is no shared host
folder, so those sources are not a cloud workflow; use the upload/capture
routes, which write through the store. The endpoint still exists but will
only see paths local to that process/container.

## Backup scope

Local-filesystem backup/restore/reset are **desktop/self-host features**:

- `services/platform/backup.py` (`build_backup`, `create_backup`,
  `boot_integrity_check`, `BackupScheduler`) accepts `BlobStore | Path` and
  raises `UnsupportedOperation` when given an object-backed store;
- `/api/v1/backup/*` and the two ad-hoc backup call sites (course delete,
  external-source upload) return `409` under an object backend instead of
  writing an archive with an empty `blobs/` section;
- `boot_integrity_check` only runs for `local`; `reset.py` refuses an object
  backend; `datastore_guard` quarantines the SQLite DB/backups but not a
  non-authoritative local blob directory.

Cloud durability is provider-native. The compose `backup` sidecar still
dumps PostgreSQL; it stops tarring `/data` when a cloud profile/object
backend is configured. An object-backup job remains a separate, future
feature.

A self-host rollback to a read-only local volume must boot with the
documented `probe=False` path; the current `create_app` does not expose
that flag, so use the migration runbook above.

## Tests and gates

```bash
cd backend
uv run pytest tests/test_object_storage_contract.py tests/test_blob_migration.py
uv run pytest tests/test_blobs.py tests/test_blobs_access.py
uv run pytest tests/test_storage_health.py
```

The fixture wall + local conformance run in normal CI. The session
`_no_network` fixture blocks outbound connects by default; the real
S3/MinIO smoke is env-gated and also requires the explicit network opt-out.
It skips cleanly when `SA_TEST_S3_*` is absent, even without the opt-out:

```bash
cd study-assistant
SA_TEST_ALLOW_NETWORK=1 SA_TEST_S3_BUCKET=nx-object-storage \
SA_TEST_S3_ENDPOINT_URL=http://127.0.0.1:19000 \
SA_TEST_S3_ACCESS_KEY_ID=test SA_TEST_S3_SECRET_ACCESS_KEY=test \
SA_TEST_S3_REGION=us-east-1 SA_TEST_S3_PATH_STYLE=true SA_TEST_S3_SSE=none \
uv run --directory backend --with boto3 pytest -q tests/test_object_storage_s3.py
```

AWS S3 (prefix-scoped IAM role or user):

```bash
AWS_PROFILE=study-test \
SA_TEST_ALLOW_NETWORK=1 \
SA_TEST_S3_BUCKET=study-assistant-test \
SA_TEST_S3_ENDPOINT_URL=https://s3.eu-north-1.amazonaws.com \
SA_TEST_S3_REGION=eu-north-1 \
SA_TEST_S3_PATH_STYLE=false \
SA_TEST_S3_SSE=AES256 \
SA_TEST_S3_PREFIX=test/ \
uv run --directory backend --with boto3 pytest -q tests/test_object_storage_s3.py
```

`SA_TEST_S3_PREFIX` must match the IAM policy prefix. The test defaults to
`conformance/` and `course-smoke/` when it is unset, so a policy scoped to
`test/*` will otherwise fail with `AccessDenied` on `PutObject`.

The run must pass both `run_conformance(store)` and the course
export/import/duplicate round-trip; run conformance before a cloud release,
while normal PRs never require provider credentials.

### Azure smoke

The Azure Blob smoke uses the same `SA_TEST_ALLOW_NETWORK=1` opt-out and
skips cleanly without credentials. Provide either a connection string or a
managed identity; `SA_TEST_AZURE_PREFIX` defaults to `smoke`:

```bash
cd study-assistant
SA_TEST_ALLOW_NETWORK=1 \
SA_TEST_AZURE_CONTAINER="$SA_AZURE_STORAGE_CONTAINER" \
SA_TEST_AZURE_CONNECTION_STRING="$SA_AZURE_STORAGE_CONNECTION_STRING" \
SA_TEST_AZURE_PREFIX=test/smoke \
uv run --directory backend --with azure-storage-blob \
  pytest -q tests/test_object_storage_azure.py
```

Managed identity instead of a connection string:

```bash
SA_TEST_ALLOW_NETWORK=1 SA_TEST_AZURE_CONTAINER=study-data \
SA_TEST_AZURE_ACCOUNT_URL=https://study.blob.core.windows.net \
SA_TEST_AZURE_ACCOUNT_NAME=study \
SA_TEST_AZURE_CREDENTIAL=managed_identity \
uv run --directory backend --with azure-storage-blob --with azure-identity \
  pytest -q tests/test_object_storage_azure.py
```

If the connection string already lives in `backend/.env`, export it with
your shell's dotenv tooling; never print or commit the value. The smoke
must pass both `run_conformance(store)` and the course
export/import/duplicate round-trip.

**Verification status:** the S3-compatible, AWS S3 and Azure
connection-string smokes (conformance + course export/import/duplicate)
are green; AWS IAM/KMS and Azure managed-identity provider smoke remain a
release gate and run through the manual cloud smoke workflow.

**Boundary:** study only. Career and health adopt the contract in their own
plans; see [deployment.md](deployment.md) for the rest of the web stack.
