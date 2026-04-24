# Installation, Verification, and Test Guide

This guide covers:

1. Deploying OCI QuickCache with Ansible.
2. Verifying systemd units, file layout, and logs.
3. Running benchmark validation with `get_latency.py` and `run_latency.sh`.

## 1) Prerequisites

## Control node (where you run Ansible)

- Python + Ansible available.
- Access to target hosts in `ansible/inventory.ini` under `[compute]`.
- SSH and privilege escalation (`become`) configured.

## Compute nodes

- Python 3 available at `/usr/bin/python3`.
- `sssd.service` running (required by shard-sync service unit).
- Required storage paths mounted as expected for your environment.

## Credentials for object storage tests

Create `~/.aws/config`:

```ini
[default]
output = json
region = us-ashburn-1
endpoint_url = https://<Object_Storage_NAMESPACE>.compat.objectstorage.us-ashburn-1.oraclecloud.com
```

Create `~/.aws/credentials`:

```ini
[default]
aws_access_key_id = <Access_Key>
aws_secret_access_key = <Secret_Key>
```

## 2) Configure deployment values

Primary runtime config file in repo:

- `ansible/roles/oci_qc/files/env.yaml`

Important keys:

- `OCI_QC_INSTALL_DIR`
- `OCI_QC_SHARD_MAP_FILE`
- `OCI_QC_LOG_FILE`
- `OCI_QC_ERR_FILE`
- `OCI_QC_MAPPING_LOG`
- `OCI_QC_CLEANUP_LOG`
- `OCI_QC_CACHE_DIR_PREFIX`
- `OCI_QC_CACHE_DIR_LOCAL`
- `OCI_QC_CACHE_DIR_NAME`
- `OCI_QC_SHARDS_PER_NODE`
- `OCI_QC_MAP_RELOAD_INTERVAL`
- `OCI_QC_CLEAN_MAX`, `OCI_QC_CLEAN_TARGET`, `OCI_QC_MAX_CACHE_FILES`

Adjust these values before deployment.

## 3) Deploy with Ansible

```bash
cd ansible
ansible-playbook -i inventory.ini site.yml
```

Optional:

```bash
ansible-playbook -i inventory.ini site.yml --check
ansible-playbook -i inventory.ini site.yml -vv
```

## 4) Post-install verification

Run on a compute node.

## Verify installed files

```bash
ls -l /opt/oci-hpc/ociqc/
```

Expected core files:

- `sitecustomize.py`
- `env.yaml`
- `oci_qc_cleanup.py`
- `manage_sharding.py`
- `migrate_shards.py`

## Verify systemd units

```bash
systemctl cat oci_qc_cleanup.service
systemctl cat oci_qc_cleanup.timer
systemctl cat oci-shard-sync.service
systemctl cat oci-shard-sync.timer
```

## Verify timers status

```bash
systemctl status oci_qc_cleanup.timer
systemctl status oci-shard-sync.timer
systemctl list-timers --all | egrep 'oci_qc_cleanup|oci-shard-sync'
```

## Verify directories and permissions

```bash
ls -ld /var/log/ociqc
ls -ld /mnt/localdisk/object_store/OCI_QC_Cache
ls -l /etc/tmpfiles.d/ociqc.conf
ls -l /etc/logrotate.d/oci_qc
```

## Verify runtime logs

```bash
tail -n 100 /var/log/ociqc/mapping.log
tail -n 100 /var/log/ociqc/cleanup.log
```

For live service logs:

```bash
journalctl -u oci_qc_cleanup.service -f
journalctl -u oci-shard-sync.service -f
```

## 5) Benchmark validation with get_latency.py

Use the `test/` directory.

```bash
cd test
```

Review and adjust at top of `get_latency.py`:

- `BUCKET`
- `ENDPOINT_URL`
- `PREFIX`
- `CONCURRENCY`
- `TOTAL_GB`
- `FILE_SIZE_KB`

## Step A: create objects

```bash
python get_latency.py put
```

## Step B: run GET benchmark

```bash
python get_latency.py get
```

## Step C: optional cleanup

```bash
python get_latency.py cleanup
```

Output file:

- `test/oci_benchmark_results.csv`

## 6) Benchmark validation with run_latency.sh

Script path:

- `test/run_latency.sh`

By default it expects:

- Miniconda at `/fss/xh/miniconda3`
- conda env `QuickCache`

If your Miniconda path differs, edit:

```bash
myconda=/fss/xh/miniconda3
```

Then run:

```bash
cd test
chmod +x run_latency.sh
./run_latency.sh
```

The script runs:

```bash
python get_latency.py get
```

and sets:

- `AWS_METADATA_SERVICE_TIMEOUT`
- `AWS_METADATA_SERVICE_NUM_ATTEMPTS`
- `OCI_QC_MAP_RELOAD_INTERVAL`

## 7) What good validation looks like

- Timers are loaded and in expected state.
- `mapping.log` receives periodic updates from shard sync.
- `cleanup.log` gets entries on cleanup service runs.
- `oci_benchmark_results.csv` receives new rows.
- Repeat GET runs show behavior consistent with cache warming.

## 8) Troubleshooting quick checks

## Service not running

```bash
systemctl status oci_qc_cleanup.service
systemctl status oci-shard-sync.service
journalctl -u oci_qc_cleanup.service -n 200
journalctl -u oci-shard-sync.service -n 200
```

## Timer confusion (enabled vs active)

```bash
systemctl is-active oci-shard-sync.timer
systemctl is-enabled oci-shard-sync.timer
```

`enabled` means starts on boot; `active` means currently running/scheduled.

## Cache path/mount issues

- Confirm `OCI_QC_CACHE_DIR_LOCAL` and `OCI_QC_CACHE_DIR_PREFIX` in deployed `env.yaml`.
- Confirm mount responsiveness and permissions.

## Credentials/endpoint issues

- Verify `~/.aws/config` and `~/.aws/credentials`.
- Verify bucket + endpoint pair in `get_latency.py`.

## 9) Operational notes

- `migrate_shards.py` does not generate shard maps; it consumes old + current maps and moves shard directories when assignments change.
- `oci-shard-sync.timer` drives periodic shard map updates.
- `oci_qc_cleanup.timer` drives periodic cache cleanup.
