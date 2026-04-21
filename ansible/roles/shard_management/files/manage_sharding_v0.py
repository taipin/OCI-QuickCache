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

        # --- 5. REVISED: Minimal Move Rebalancing Logic ---
        new_hosts = sorted(mounts)
        n_new = len(new_hosts)
        base, rem = divmod(total_shards, n_new)
        
        # Determine target capacity per host
        targets = {h: base + (1 if i < rem else 0) for i, h in enumerate(new_hosts)}

        new_map = {}
        counts = {h: 0 for h in new_hosts}
        orphaned_ids = []

        if old_map:
            # Keep shards on their current host if it's still available and has capacity
            for sid_str, oh in old_map.items():
                if oh in targets and counts[oh] < targets[oh]:
                    new_map[sid_str] = oh
                    counts[oh] += 1
                else:
                    orphaned_ids.append(sid_str)
        else:
            # For a fresh init, just collect all IDs to be distributed
            orphaned_ids = [str(i) for i in range(total_shards)]

        # Assign shards that lost their home or were moved for balancing
        for sid_str in orphaned_ids:
            for h in new_hosts:
                if counts[h] < targets[h]:
                    new_map[sid_str] = h
                    counts[h] += 1
                    break
        # ----------------------------------------------------

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
