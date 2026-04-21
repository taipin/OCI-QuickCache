#!/usr/bin/env python3
import os, json, glob, yaml, time, shutil, fcntl, socket

# --- CONFIGURATION ---
ENV_PATH = "/opt/oci-hpc/ociqc/env.yaml"

def is_valid_shard_mount(path):
    """
    Checks if path is a directory and either:
    1. Resides under /tmp/
    2. Is an active mount point NOT on the same device as root.
    """
    if not os.path.isdir(path):
        return False
    
    # Check if it is a subdirectory of /tmp/
    if path.startswith("/tmp/"):
        return True

    # Otherwise, require it to be a mount point that is not the root partition
    if not os.path.ismount(path):
        return False
    
    try:
        root_dev = os.stat('/').st_dev
        path_dev = os.stat(path).st_dev
        return root_dev != path_dev
    except Exception:
        return False

def run_sync():
    # Load configuration
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
        """Audits changes to the shared system log."""
        os.makedirs(os.path.dirname(MAPPING_LOG), exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(MAPPING_LOG, 'a') as f:
            f.write(f"[{ts}] [{HOSTNAME}] {msg}\n")

    # 1. Ensure Shared Directory exists
    os.makedirs(SHARED_DIR, exist_ok=True)

    # 2. Acquire Shared Lock (Exclusive, Non-blocking)
    lock_f = open(LOCK_FILE, 'w')
    try:
        # Prevents multiple nodes from updating the map simultaneously
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Exit quietly; another node is already performing the sync
        return 

    try:
        # 3. Discover valid shard mounts (Excludes root partition folders)
        mounts = sorted([m for m in glob.glob(PATTERN) if is_valid_shard_mount(m)])
        
        if not mounts:
            log_change("CRITICAL: No valid shard mounts detected (excluding root).")
            return

        # 4. Load old map if it exists
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

        # 5. Always create new map - return if it's the same as the old map
        new_map = {str(i): mounts[i % len(mounts)] for i in range(total_shards)}
        
        if old_map == new_map:
            return 

        # 6. We have a real new map - archive the old and update the map file
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
