#!/usr/bin/env python3
import os, json, glob, yaml, time, shutil, fcntl, socket, subprocess

# --- CONFIGURATION ---
ENV_PATH = "/opt/oci-hpc/ociqc/env.yaml"

def is_path_alive(path, timeout_sec=2):
    """Uses Linux 'timeout' to check if a path is responsive. 
    Required for 'hard' mounts that hang indefinitely."""
    try:
        # 'test -d' checks directory; 'timeout' kills it if it hangs
        subprocess.run(["timeout", str(timeout_sec), "test", "-d", path], 
                       check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False

def is_valid_shard_mount(path):
    """Checks validity of mount point with hang protection."""
    # 1. Protection for hard mounts: Check if path is responsive
    # Skip for /tmp which is usually local/fast
    if not path.startswith("/tmp/") and not is_path_alive(path):
        return "TIMEOUT"

    if not os.path.isdir(path):
        return False

    # 2. Local /tmp bypass
    if path.startswith("/tmp/"):
        return True

    # 3. Mount and Device Check
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

    # 1. Shared Storage Health Check
    if not is_path_alive(SHARED_DIR, timeout_sec=4):
        print(f"Aborting: Shared directory {SHARED_DIR} unreachable.")
        return

    os.makedirs(SHARED_DIR, exist_ok=True)

    # 2. Acquire Shared Lock (Exclusive, Non-blocking)
    lock_f = open(LOCK_FILE, 'w')
    try:
        # LOCK_NB prevents hanging if another node or the FS is stuck
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        return

    try:
        # 3. Discovery: Use 'ls' on parent to avoid shell-level wildcard hang
        parent_dir = os.path.dirname(cfg['OCI_QC_CACHE_DIR_PREFIX']) or "/"
        prefix = os.path.basename(cfg['OCI_QC_CACHE_DIR_PREFIX'])
        
        # We capture the output of 'ls' even if it gets killed by timeout
        ls_cmd = f"timeout 5 ls -1 {parent_dir}"
        proc = subprocess.run(ls_cmd, shell=True, capture_output=True, text=True)
        
        # Get items that successfully printed before any hang/timeout
        items = proc.stdout.strip().split('\n')
        possible_paths = [os.path.join(parent_dir, i) for i in items if i.startswith(prefix)]

        mounts = []
        for p in sorted(possible_paths):
            if not p: continue
            status = is_valid_shard_mount(p)
            if status == "TIMEOUT":
                log_change(f"WARNING: Node {p} is HANGING. Excluding from map.")
            elif status is True:
                mounts.append(p)

        if not mounts:
            log_change("CRITICAL: No valid shard mounts detected.")
            return

        # 4. Load old map safely
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

        # 5. Minimal Move Rebalancing Logic
        new_hosts = sorted(mounts)
        n_new = len(new_hosts)
        base, rem = divmod(total_shards, n_new)
        targets = {h: base + (1 if i < rem else 0) for i, h in enumerate(new_hosts)}

        new_map = {}
        counts = {h: 0 for h in new_hosts}
        orphaned_ids = []

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

        # 6. Archive and Update
        if old_map:
            ts = time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(MAP_FILE, f"{MAP_FILE}.{ts}.bak")

        tmp = MAP_FILE + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(new_map, f, indent=4)
        os.rename(tmp, MAP_FILE)
        log_change(f"SUCCESS: Map updated. Nodes: {len(mounts)}.")

    except Exception as e:
        log_change(f"ERROR: Sync process failed: {str(e)}")
    finally:
        fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()

if __name__ == "__main__":
    run_sync()
