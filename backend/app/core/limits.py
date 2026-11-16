"""Host upload limits shared by services, storage bootstrap and billing-free tests.

Keeping the ceiling in one module avoids the contract's 100 MB default
silently capping a study deployment (or a directly constructed
``BlobStore(Path)``) below the 200 MB the upload API advertises.
"""

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_UPLOAD_MB = MAX_UPLOAD_BYTES // (1024 * 1024)
