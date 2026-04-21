#!/usr/bin/env python3
import os, json, yaml, subprocess, sys, shutil, signal

# --- CONFIGURATION ---
ENV_PATH = os.getenv("OCI_QC_ENV_PATH") or os.path.join(os.path.dirname(__file__), "env.yaml")

with open(ENV_PATH, 'r') as y:
    cfg = yaml.safe_load(y)

# Get current system user for the directory path
USER_NAME = os.environ.get("USER") or os.getlogin()

# --- TIMEOUT HANDLING ---
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException

def migrate(source_map_path, dry_run=True):
    # Load source (old) and target (current) maps
    with open(source_map_path, 'r') as f:
        old_map = json.load(f)
    with open(cfg['OCI_QC_SHARD_MAP_FILE'], 'r') as f:
        new_map = json.load(f)

    cache_root = cfg['OCI_QC_CACHE_DIR_NAME']
    total_moved_bytes = 0
    
    # Set up timeout for hanging mounts
    signal.signal(signal.SIGALRM, timeout_handler)

    for sid_str, new_mount in new_map.items():
        old_mount = old_map.get(sid_str)
        
        # Only move if the shard's assigned mount has changed
        if old_mount and old_mount != new_mount:
            shard_idx = int(sid_str)
            shard_subdir = f"{shard_idx:03d}"
            
            src_shard_path = os.path.join(old_mount, cache_root, USER_NAME, shard_subdir)
            dst_shard_parent = os.path.join(new_mount, cache_root, USER_NAME)
            dst_shard_path = os.path.join(dst_shard_parent, shard_subdir)

            # Check if source exists with a timeout (prevents hanging on dead source)
            signal.alarm(5)
            try:
                if not os.path.exists(src_shard_path):
                    signal.alarm(0)
                    continue
            except TimeoutException:
                print(f"SKIPPING Shard {shard_subdir}: Source mount {old_mount} is HANGING.")
                signal.alarm(0)
                continue
            finally:
                signal.alarm(0)

            # Calculate size for the final summary
            shard_size = 0
            try:
                for dirpath, _, filenames in os.walk(src_shard_path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        shard_size += os.path.getsize(fp)
            except: pass

            print(f"Moving Shard {shard_subdir} ({shard_size / 1e6:.1f} MB): {old_mount} -> {new_mount}")
            
            if not dry_run:
                os.makedirs(dst_shard_parent, exist_ok=True)
                try:
                    # rsync handles its own network timeouts better than os.rename
                    subprocess.run([
                        "rsync", "-av", "--remove-source-files", 
                        src_shard_path + "/", dst_shard_path + "/"
                    ], check=True)
                    
                    # Clean up empty source shard directory
                    if os.path.exists(src_shard_path):
                        shutil.rmtree(src_shard_path)
                    
                    total_moved_bytes += shard_size
                except subprocess.CalledProcessError as e:
                    print(f"ERROR: Migration failed for Shard {shard_subdir}: {e}")
                    # We continue to next shard instead of exiting so other moves can finish

    print("\n-------------------------------------------")
    print(f"Migration Summary ({'LIVE' if not dry_run else 'DRY RUN'}):")
    print(f"Total data moved: {total_moved_bytes / 1e9:.2f} GB")
    print("-------------------------------------------")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: migrate_shards.py <source_map_json> [--live]")
        sys.exit(1)
    
    source_map = sys.argv[1]
    is_dry = "--live" not in sys.argv
    
    if is_dry:
        print("--- DRY RUN MODE (No files will be moved) ---")
        
    migrate(source_map, dry_run=is_dry)
