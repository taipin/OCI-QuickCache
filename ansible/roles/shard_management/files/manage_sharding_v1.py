#!/usr/bin/env python3
import os, json, glob, yaml, time, shutil, fcntl, socket, signal

# --- CONFIGURATION ---
ENV_PATH = "/opt/oci-hpc/ociqc/env.yaml"

# Custom exception for NFS timeouts
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException

def is_valid_shard_mount(path, timeout=5):
    """
    Checks if path is a directory and either:
    1. Resides under /tmp/
    2. Is an active mount point NOT on the same device as root.
    Includes a timeout to prevent hanging on dead NFS mounts.
    """
    if not os.path.isdir(path):
        return False

    if path.startswith("/tmp/"):
        return True

    # Set alarm to break out of hanging system calls (hard mounts)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)

    try:
        if not os.path.ismount(path):
            signal.alarm(0)
            return False

        root_dev = os.stat('/').st_dev
        path_dev = os.stat(path).st_dev
        
        signal.alarm(0)
        return root_dev != path_dev

    except TimeoutException:
        # We don't log to the system log here to keep this function side-effect free,
        # but we return a specific failure that run_sync will catch.
        return "TIMEOUT"
    except Exception:
        return False
    finally:
        signal.alarm(0)

def run_sync():
    if not os.path.exists(ENV_PATH):
        print(f"Error: Configuration file {ENV_PATH} not found.")
        return

    with open(ENV_PATH, 'r') as y:
        cfg = yaml.safe_load(y)

    MAP_FILE = cfg['OCI_QC_SHARD_MAP_FILE']
    SHARED_DIR = os.path.dirname(MAP_FILE)
    LOCK_FILE = MAP_FILE + ".lock"
    MAPPING_LOG = cfg['OCI_QC_MAPPING_LOG']
    PATTERN = f"{cfg['OCI_QC_CACHE_DIR_PREFIX']}*"
    SHARDS_PER_NODE = cfg['OCI_QC_SHARDS_PER_NODE']
    HOSTNAME = socket.gethostname()

    def log_change(msg):
        os.makedirs(os.path.dirname(MAPPING_LOG), exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(MAPPING_LOG, 'a') as f:
            f.write(f"[{ts}] [{HOSTNAME}] {msg}\n")

    os.makedirs(SHARED_DIR, exist_ok=True)
    lock_f = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return

    try:
        # --- REVISED: Discover mounts with timeout logging ---
        mounts = []
        possible_paths = sorted(glob.glob(PATTERN))
        
        for p in possible_paths:
            status = is_valid_shard_mount(p)
            if status == "TIMEOUT":
                log_change(f"WARNING: Mount check timed out for {p}. Node may be down.")
            elif status is True:
                mounts.append(p)
        # -----------------------------------------------------

        if not mounts:
            log_change("CRITICAL: No valid shard mounts detected."); return

        old_map = None
        if os.path.exists(MAP_FILE):
            try:
                with open(MAP_FILE, 'r') as f:
                    old_map = json.load(f)
            except Exception as e:
                log_change(f"WARNING: Map file unreadable ({e}), re-initializing.")

        if old_map:
            total_shards = len(old_map)
        else:
            total_shards = len(mounts) * SHARDS_PER_NODE
            log_change(f"INIT: Creating new map with {total_shards} fixed shards.")

        new_hosts = sorted(mounts)
        n_new = len(new_hosts)
        base, rem = divmod(total_shards, n_new)
        targets = {h: base + (1 if i < rem else 0) for i, h in enumerate(new_hosts)}

        new_map, counts, orphaned_ids = {}, {h: 0 for h in new_hosts}, []

        if old_map:
            for sid_str, oh in old_map.items():
                if oh in targets and counts[oh] < targets[oh]:
                    new_map[sid_str] = oh
                    counts[oh] += 1
                else:
                    orphaned_ids.append(sid_str)
        else:
            orphaned_ids = [str(i) for i in range(total_shards)]

        for sid_str in orphaned_ids:
            for h in new_hosts:
                if counts[h] < targets[h]:
                    new_map[sid_str] = h
                    counts[h] += 1
                    break

        if old_map == new_map:
            return

        if old_map:
            ts = time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(MAP_FILE, f"{MAP_FILE}.{ts}.bak")

        tmp = MAP_FILE + ".tmp"
        with open(tmp, 'w') as f: json.dump(new_map, f, indent=4)
        os.rename(tmp, MAP_FILE)
        log_change(f"SUCCESS: Map updated. Distributed {total_shards} shards across {len(mounts)} nodes.")
    except Exception as e:
        log_change(f"ERROR: Sync process failed: {str(e)}")
    finally:
        fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()

if __name__ == "__main__":
    run_sync()
