# Environment Variables and Global Parameters Reference

This document consolidates configuration keys from:

- `ansible/roles/oci_qc/files/env.yaml`
- `ansible/roles/oci_qc/files/sitecustomize.py`
- `ansible/roles/oci_qc/files/oci_qc_cleanup.py`
- `ansible/roles/shard_management/files/manage_sharding.py`
- `ansible/roles/shard_management/files/migrate_shards.py`

## Environment/config variables

| Name | Default | Owner | Runtime Override | Used In | Description |
|---|---|---|---|---|---|
| `OCI_QC_SHARD_MAP_FILE` | `/fss/ociqc/shard_map.json` | root | N  | ansible, app, manage, migrate | Persistent shard-to-filesystem map |
| `OCI_QC_INSTALL_DIR` | `/opt/oci-hpc/ociqc` | root | N | ansible | Install path for deployed scripts/config |
| `OCI_QC_LOG_FILE` | `/var/log/ociqc/cache_log.csv` | user/app | Y | app | Cache HIT/MISS audit log |
| `OCI_QC_ERR_FILE` | `/var/log/ociqc/cache_err.csv` | user/app | Y | app | Cache error log |
| `OCI_QC_MAPPING_LOG` | `/var/log/ociqc/mapping.log` | root | N | ansible, manage | Shard-map sync log |
| `OCI_QC_CLEANUP_LOG` | `/var/log/ociqc/cleanup.log` | root | N | cleanup, ansible | Cache cleanup service log |
| `OCI_QC_CACHE_DIR_PREFIX` | `/object_store_dens` | root | N | manage | Prefix for discovering cache mount candidates |
| `OCI_QC_CACHE_DIR_LOCAL` | `/mnt/localdisk/object_store` | root | N | ansible, cleanup | Local storage root used for cache |
| `OCI_QC_CACHE_DIR_NAME` | `OCI_QC_Cache` | root | N | ansible, app, cleanup, migrate | Cache subdirectory name |
| `OCI_QC_CACHE_USE_USER_SUBDIR` | `false` | root/app | Y | app, migrate | If `true`, cache path includes per-user segment (`.../OCI_QC_Cache/<user>/...`); if `false`, user segment is omitted |
| `OCI_QC_SHARDS_PER_NODE` | `4` | root | N | manage | Number of shard slots per discovered mount/node |
| `OCI_QC_SHARD_PREFIX` | `""` | user/app | N | app | Optional prefix for shard directory naming |
| `OCI_QC_SHARD_FORM` | `03d` | user/app | N | app | Shard id format string (`000`, `001`, ...) |
| `OCI_QC_MAX_CACHE_AGE` | `36000000` | user/app | Y | app | TTL in seconds before cache entry is considered expired |
| `OCI_QC_MAP_RELOAD_INTERVAL` | `600` | user/app | Y | app | Interval (seconds) for app to reload shard map from a global file to memory. map file is updated by sharding service (timer) |
| `OCI_QC_CLEAN_MAX` | `0.9` | root | Y | cleanup | Cache space usage (disk/full ratio) to trigger cleanup |
| `OCI_QC_CLEAN_TARGET` | `0.7` | root | Y | cleanup | Cleanup target ratio to stop deletion |
| `OCI_QC_MAX_CACHE_FILES` | `500000000` | root | Y | cleanup | File-count threshold for cleanup |
| `OCI_QC_ENV_PATH` | `<script_dir>/env.yaml` (most scripts) | root/user | Y | app, cleanup, migrate | Explicit path to config YAML for scripts supporting override |
| `OCI_QC_DEBUG_LEVEL` | `1` | user/app | Y | app | Print/log verbosity for `sitecustomize.py` (`0` silent, higher = more logs) |

## Global/runtime parameters (non-env)

| Name | Default/Init | Defined In | Used In | Description |
|---|---|---|---|---|
| `OCI_QC_NUM_SHARDS` | `1` (then set from map size) | `sitecustomize.py` | app cache routing | Current number of shards in memory |
| `OCI_QC_SHARD_MAP` | `None` (then loaded from file) | `sitecustomize.py` | app cache routing | In-memory shard->mount mapping |
| `OCI_QC_LAST_CHECK_TIME` | `0` | `sitecustomize.py` | app map refresh | Last time map was refreshed |
| `CACHE_USER_NAME` | current OS user | `sitecustomize.py` | app path layout | User namespace segment for cache path when `OCI_QC_CACHE_USE_USER_SUBDIR=true` |
| `USE_DIRECT_IO` | `False` | `sitecustomize.py` | app read path | Toggle for direct I/O reads on cache files |
| `OCI_QC_ROOT_DEV_ID` | `os.stat('/').st_dev` | `sitecustomize.py` | mount validation | Reference device id to reject root-device mounts |
| `ENV_PATH` | script-specific | multiple scripts | config load | Resolved config file path used by each script |
| `CFG` | parsed YAML dict | `sitecustomize.py`, `oci_qc_cleanup.py` | runtime config | In-memory loaded configuration |

## Script-specific notes

- `manage_sharding.py` currently uses a fixed `ENV_PATH = "/opt/oci-hpc/ociqc/env.yaml"`.
- `migrate_shards.py` and `oci_qc_cleanup.py` support `OCI_QC_ENV_PATH` override.
- `sitecustomize.py` supports both `env.yaml` values and selected env var overrides (`OCI_QC_LOG_FILE`, `OCI_QC_ERR_FILE`, `OCI_QC_MAX_CACHE_AGE`, `OCI_QC_MAP_RELOAD_INTERVAL`, `OCI_QC_DEBUG_LEVEL`).
- Directory permission model in `oci_qc` role:
- log dir and cache dir are created with mode `3775`.
- default ACL (`group: ociqc-group`, `rwX`, default ACL) is applied on log dir.
- mapping-log parent dir remains mode `0755`.
