# OCI QuickCache

OCI QuickCache adds host-local object caching for S3-compatible `GetObject` workloads by monkey-patching the Botocore S3 client path. It is designed for multi-node compute clusters where repeated reads of the same objects benefit from local cache hits and shard-aware placement.

## What this repo contains

- `ansible/`: deployment and operations automation.
- `test/`: benchmark and validation scripts (latency/throughput runs).
- `docs/`: architecture diagrams and operator docs.

## Core components

- Runtime cache hook: `ansible/roles/oci_qc/files/sitecustomize.py`
- Cleanup worker: `ansible/roles/oci_qc/files/oci_qc_cleanup.py`
- Shard map sync: `ansible/roles/shard_management/files/manage_sharding.py`
- Shard migration helper: `ansible/roles/shard_management/files/migrate_shards.py`

## How it works (high level)

1. Application issues `GetObject` via boto3/botocore.
2. `sitecustomize.py` intercepts S3 `GetObject` calls.
3. A shard is selected from `shard_map.json` based on hashed object key.
   Cache path can include per-user subdirectory (configurable via `OCI_QC_CACHE_USE_USER_SUBDIR`).
4. Cache path is checked:
- Fresh: serve locally (`HIT` / `HIT_RANGE`).
- Expired: conditional remote check (supports 304 refresh path).
- Miss: fetch remotely, tee stream to temp file, then atomic rename into cache.
5. Cache audit and error logs are written.

## Cluster control loops

- `oci-shard-sync.timer` runs `manage_sharding.py` periodically to discover healthy mounts and update shard assignments.
- `oci_qc_cleanup.timer` runs `oci_qc_cleanup.py` periodically to enforce disk/inode thresholds.
- `migrate_shards.py` is operator-invoked to move shard directories after map changes.

## Deploy with Ansible

```bash
cd ansible
ansible-playbook -i inventory.ini site.yml
```

Playbook target group: `compute` (see `ansible/inventory.ini`).

## After deployment (expected)

- Install dir: `/opt/oci-hpc/ociqc/`
- Systemd units:
- `/etc/systemd/system/oci_qc_cleanup.service`
- `/etc/systemd/system/oci_qc_cleanup.timer`
- `/etc/systemd/system/oci-shard-sync.service`
- `/etc/systemd/system/oci-shard-sync.timer`
- Log dir: `/var/log/ociqc/`
- Shared map path: `/fss/ociqc/shard_map.json` (from `env.yaml`)

## Testing entry points

- `test/get_latency.py`
- `test/run_latency.sh`

See full operator guide: [`docs/install-verify-test.md`](docs/install-verify-test.md)

## Documentation

- One-pager: [`docs/monkey-patch-caching-one-pager.md`](docs/monkey-patch-caching-one-pager.md)
- Install/verify/test guide: [`docs/install-verify-test.md`](docs/install-verify-test.md)
