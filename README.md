**OCI Quick Cache (oci_qc)**

This repository contains an Ansible role and helper scripts that provide a universal, local S3 caching layer and a background cleanup utility.

**Key Files**
- **Role:** [ansible/roles/oci_qc](ansible/roles/oci_qc)
- **Site-wide Python S3 cache integration:** [ansible/roles/oci_qc/files/sitecustomize.py](ansible/roles/oci_qc/files/sitecustomize.py)
- **Cache cleanup utility:** [ansible/roles/oci_qc/files/oci_qc_cleanup.py](ansible/roles/oci_qc/files/oci_qc_cleanup.py)

**Features (from `sitecustomize.py`)**
- **Universal S3 cache:** Monkey-patches `botocore.client.BaseClient._make_api_call` to add a local cache layer for S3 `GetObject` calls.
- **Deterministic sharding:** Maps S3 resources (bucket+key) via MD5 hashing to shards distributed across discovered mount points.
- **Shard discovery & refresh:** Discovers cache mount points using a filesystem glob and validates mounts; writes an atomic shard map and refreshes it periodically.
- **Atomic streaming (TEE):** Streams S3 responses to the client while teeing the response to a temp file that is atomically renamed when complete.
- **Conditional 304 checks:** When cache is expired, does an `If-Modified-Since` / `If-None-Match` conditional request to avoid unnecessary downloads and refresh cache on `304`.
- **Byte-range support:** Honors Range requests and serves 206 responses from cache when applicable.
- **Direct I/O option:** Experimental `O_DIRECT`-based reader for aligned reads (controlled by `USE_DIRECT_IO`).
- **Path validation & graceful fallback:** Validates path length and mount availability; falls back to network on failures and logs error reasons.
- **CSV logging:** Audit events and errors are appended to CSV files for monitoring (`OCI_QC_LOG_FILE`, `OCI_QC_ERR_FILE`).

**Features (from `oci_qc_cleanup.py`)**
- **Disk and inode-aware cleanup:** Inspects disk usage and inode counts to determine if cleanup is needed.
- **LRU-style removal:** Walks cache directories and removes least-recently-accessed files until target free space / file count is reached.
- **Configurable thresholds:** Adjustable full/target ratios and maximum file limits.
- **Safe pruning:** Skips temp/lock/etag files, removes matching `.etag` files when their paired object is removed, and prunes empty directories.
- **Logging:** Writes progress and statistics to `/var/log/ociqc/cleanup.log`.

**Configuration (important environment variables & defaults)**
- **Sitecustomize / runtime**
	- **OCI_QC_MAX_CACHE_AGE:** TTL in seconds (default: `360000`).
	- **OCI_QC_CACHE_DIR_PREFIX:** Mount discovery glob prefix (default: `/tmp/cache_test/fs-`).
	- **OCI_QC_SHARD_PREFIX:** Directory prefix for shards (default: `shard_`).
	- **OCI_QC_SHARDS_PER_NODE:** Shards per mount (default: `4`).
	- **OCI_QC_SHARD_MAP_FILE:** Shard map file (default: `oci_qc_shard_map.json`).
	- **OCI_QC_LOG_FILE / OCI_QC_ERR_FILE:** CSV audit and error logs (defaults: `boto3_cache_audit.csv`, `boto3_cache_errors.csv`).
	- **OCI_QC_SHARD_MAP_REFRESH_INTERVAL:** Seconds between shard-map refreshes (default: `600`).
	- **USE_DIRECT_IO:** `True`/`False` to enable `O_DIRECT` (default: `False`).

- **Cleanup utility**
	- **OCI_QC_CACHE_DIR:** Colon-separated list of cache root directories (default in script: `/mnt/localdisk/object_store/OCI_QC_Cache`).
	- **OCI_QC_MAX_FULL:** Disk full ratio that triggers cleanup (default: `0.9`).
	- **OCI_QC_CLEAN_TARGET:** Target ratio to reach after cleanup (default: `0.7`).
	- **OCI_QC_MAX_CACHE_NO:** Maximum file-count threshold (default: `1000`).

Installation & quick test

1) Enable the Python S3 cache (two options):

- Temporary / per-shell (good for testing on a single node): add the role `files` dir to `PYTHONPATH` so `sitecustomize.py` can be imported by processes:

```bash
export PYTHONPATH="$(pwd)/ansible/roles/oci_qc/files:$PYTHONPATH"
python3 -c "import sitecustomize; print('SITECUSTOMIZE loaded')"
```

- System-wide (not recommended): install `sitecustomize.py` to a directory on Python's import path (example shown for a typical Linux install; adjust Python version/path as needed):

```bash
sudo cp ansible/roles/oci_qc/files/sitecustomize.py /usr/local/lib/python3.9/site-packages/sitecustomize.py
```

- System-wide (recommended): install `sitecustomize.py` to a customized directory on all compute nodes via ansible (see ansible/README.md for more details):

```bash
cd ansible
vi inventory.ini site.yml
ansible-playbook -i inventory.ini site.yml
```

After installation, any Python process that imports `boto3`/`botocore` will use the caching logic for `GetObject` where applicable.

2) Run the cleanup utility manually (quick smoke test):

```bash
OCI_QC_CACHE_DIR=/tmp/cache_test/fs-0 python3 ansible/roles/oci_qc/files/oci_qc_cleanup.py
```

3) Using the Ansible role

- This repository includes an Ansible playbook and role under `ansible/`. If you want to deploy the files to targets, run the playbook in this repo (adjust inventory and variables as needed):

```bash
ansible-playbook -i ansible/inventory.ini ansible/site.yml
```

Notes & next steps
- The `sitecustomize.py` is intentionally aggressive (monkey-patches `botocore`) — test in a staging environment before rolling to production.
- The role also contains systemd unit and timer templates that can schedule `oci_qc_cleanup.py` runs; these can be enabled via the playbook.
- > **Warning:** Be extremely careful when setting the Ansible variable `oci_qc_cache_dirs` (environment variable `OCI_QC_CACHE_DIRS`). Its default value is `/mnt/localdisk/object_store/OCI_QC_Cache`. Do NOT set this to directories that contain non-cache data — those files may be deleted by the cleanup service.
- Logs and CSV outputs are local files; consider shipping them to your monitoring system for visibility.
