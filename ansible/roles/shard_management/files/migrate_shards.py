#!/usr/bin/env python3
import os, json, yaml, subprocess, sys, shutil

# --- CONFIGURATION ---
ENV_PATH = os.getenv("OCI_QC_ENV_PATH") or os.path.join(os.path.dirname(__file__), "env.yaml")
#ENV_PATH = "/opt/oci-hpc/ociqc/env.yaml"

def is_path_alive(path, timeout_sec=3):
    """Checks if a mount is responsive to avoid hangs."""
    try:
        subprocess.run(["timeout", str(timeout_sec), "test", "-d", path], 
                       check=True, capture_output=True)
        return True
    except:
        return False

def migrate(source_map_path, dry_run=True):
    with open(ENV_PATH, 'r') as y:
        cfg = yaml.safe_load(y)
    
    current_map_path = cfg['OCI_QC_SHARD_MAP_FILE']
    cache_root_name = cfg.get('OCI_QC_CACHE_DIR_NAME', 'OCI_QC_Cache')

    try:
        with open(source_map_path, 'r') as f:
            old_map = json.load(f)
        with open(current_map_path, 'r') as f:
            new_map = json.load(f)
    except Exception as e:
        print(f"Error loading JSON maps: {e}")
        return

    total_moved_bytes = 0
    diff_count = 0
    
    mode_label = "DRY RUN" if dry_run else "LIVE"
    print(f"--- Migration: {mode_label} ---")

    # Iterate through shards to find movements
    for sid_str, new_mount in new_map.items():
        old_mount = old_map.get(sid_str)
        nm, om = new_mount.rstrip('/'), (old_mount.rstrip('/') if old_mount else None)

        if om and om != nm:
            diff_count += 1
            shard_subdir = f"{int(sid_str):03d}"
            
            # Skip if source mount is dead
            if not is_path_alive(om):
                print(f"SKIPPING Shard {shard_subdir}: Source mount {om} is DOWN.")
                continue
            
            # Look for user folders inside the cache root
            old_cache_root = os.path.join(om, cache_root_name)
            if not os.path.exists(old_cache_root):
                continue

            for user_dir in os.listdir(old_cache_root):
                src_path = os.path.join(old_cache_root, user_dir, shard_subdir)
                
                if os.path.isdir(src_path):
                    # --- FIXED: Correct variable used for size calculation ---
                    size = 0
                    try:
                        res = subprocess.run(["timeout", "5", "du", "-sb", src_path], 
                                             capture_output=True, text=True)
                        if res.returncode == 0:
                            size = int(res.stdout.split()[0])
                    except: 
                        pass

                    total_moved_bytes += size
                    print(f"{'Plan' if dry_run else 'Moving'}: Shard {shard_subdir} (User: {user_dir}, {size/1e6:.2f} MB)")

                    if not dry_run:
                        dst_path = os.path.join(nm, cache_root_name, user_dir, shard_subdir)
                        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                        
                        try:
                            # Migrate data
                            subprocess.run(["rsync", "-av", "--remove-source-files", 
                                          src_path + "/", dst_path + "/"], check=True)
                            # Cleanup empty directory
                            if os.path.exists(src_path):
                                shutil.rmtree(src_path)
                        except Exception as e:
                            print(f"  ERROR moving {src_path}: {e}")

    print("\n" + "="*45)
    print(f"Migration Summary ({mode_label})")
    print(f"Total Shards affected: {diff_count}")
    print(f"Total Data moved: {total_moved_bytes / 1e9:.3f} GB")
    print("="*45)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: migrate_shards.py <old_map.json> [--live]")
    else:
        # sys.argv[1] is the map file, we check for --live in the whole list
        migrate(sys.argv[1], dry_run=("--live" not in sys.argv))

