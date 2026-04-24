# OCI QuickCache Ansible Deployment

## Purpose

Deploy OCI QuickCache runtime and shard-management components onto compute nodes:

- Cache monkey-patch runtime (`sitecustomize.py`)
- Cleanup worker + timer (`oci_qc_cleanup.service/.timer`)
- Shard sync worker + timer (`oci-shard-sync.service/.timer`)
- Logrotate and directory/ACL setup

Playbook: [site.yml](site.yml)  
Inventory: [inventory.ini](inventory.ini)

## Configuration source (`env.yaml`)

`roles/oci_qc/files/env.yaml` is the single configuration source used in two places:

- Deployment-time variables in Ansible (`site.yml` uses it via `vars_files`)
- Runtime config copied to each node at:
  - `/opt/oci-hpc/ociqc/env.yaml`

Runtime Python scripts read that deployed file, including:

- `sitecustomize.py`
- `oci_qc_cleanup.py`
- `manage_sharding.py`
- `migrate_shards.py` (also supports `OCI_QC_ENV_PATH` override)

## Prerequisites

- Ansible control host with Python + Ansible installed.
- Target hosts reachable as group `compute` in `inventory.ini`.
- Required shared/local filesystems mounted on target nodes.
- SSSD/LDAP group lookup working for `ociqc_group_name` (the role validates this with `getent`).

### Critical prerequisite: `OCI_QC_CACHE_DIR_PREFIX`

`OCI_QC_CACHE_DIR_PREFIX` is used by `manage_sharding.py` to discover shard mount candidates.  
Example:

```yaml
OCI_QC_CACHE_DIR_PREFIX: "/object_store_dens"
```

With that value, the sync process scans the parent directory and matches entries beginning with `object_store_dens` (for example, `/object_store_dens1`, `/object_store_dens2`, ...).

Requirements:

- Mount paths must follow a consistent prefix naming pattern across nodes.
- Those paths must exist and be responsive on each node.
- Non-responsive or invalid mounts are excluded from shard assignment.

If this prefix is wrong, shard discovery fails or becomes partial, and `shard_map.json` will be incorrect/incomplete.

## Run

```bash
cd ansible
ansible-playbook -i inventory.ini site.yml
```

Useful flags:

- `--check` for dry run
- `-vv` for verbose output

## What the playbook configures

- Creates log directory (`3775`) and default ACLs for group sharing.
- Creates local cache root directory (`3775`), and cache ACL defaults when `OCI_QC_CACHE_USE_USER_SUBDIR` is enabled.
- Creates/touches log files with group ownership and mode `0664`.
- Copies runtime scripts to `OCI_QC_INSTALL_DIR` (default `/opt/oci-hpc/ociqc`).
- Deploys and enables:
  - `oci_qc_cleanup.timer`
  - `oci-shard-sync.timer`
- Deploys systemd service units, tmpfiles config, and logrotate config.

## Verify after deployment

```bash
sudo systemctl status oci_qc_cleanup.timer
sudo systemctl status oci_qc_cleanup.service
sudo systemctl status oci-shard-sync.timer
sudo systemctl status oci-shard-sync.service
```

```bash
sudo systemctl list-timers --all | egrep 'oci_qc_cleanup|oci-shard-sync'
```

```bash
sudo journalctl -u oci_qc_cleanup.service -f
sudo journalctl -u oci-shard-sync.service -f
```

## Notes

- If `ansible.posix.acl` is used, ensure ACL support is available (role installs `acl` package on Ubuntu).
- If `ociqc_group_name` is not resolvable, deployment will fail early by design.

