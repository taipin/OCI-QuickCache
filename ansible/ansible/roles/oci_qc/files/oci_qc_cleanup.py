import os
import logging

LOG_FILE = "/var/log/ociqc/cleanup.log"
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def cleanup_cache():
    cache_dirs_str = os.environ.get('OCI_QC_CACHE_DIR', '/mnt/localdisk/object_store/OCI_QC_Cache')
    if not cache_dirs_str:
        logging.warning("OCI_QC_CACHE_DIR not set. Skipping.")
        return
    
    cache_dirs = [d.strip() for d in cache_dirs_str.split(':') if d.strip()]
    max_full_ratio = float(os.environ.get('OCI_QC_MAX_FULL', 0.9))
    target_ratio = float(os.environ.get('OCI_QC_CLEAN_TARGET', 0.7))
    max_files_limit = int(os.environ.get('OCI_QC_MAX_CACHE_NO', 1000))

    for cache_dir in cache_dirs:
        if not os.path.exists(cache_dir):
            continue

        try:
            usage = os.statvfs(cache_dir)
            
            # 1. Disk Space Ratio (Bytes)
            total_blocks = usage.f_blocks
            avail_blocks = usage.f_bavail
            disk_full_ratio = 1 - (avail_blocks / total_blocks) if total_blocks > 0 else 0
            
            # 2. Inode Usage (Fast File Count Proxy)
            total_inodes = usage.f_files
            avail_inodes = usage.f_favail
            used_inodes = total_inodes - avail_inodes
            
            logging.info(f"Stats for {cache_dir}: Disk usage: {disk_full_ratio:.2%}, Total used inodes on disk: {used_inodes}")

            # Check if we can skip the heavy scan
            # We skip ONLY if disk space is fine AND total disk inodes are below our file limit
            if disk_full_ratio < max_full_ratio and used_inodes < max_files_limit:
                continue 

            total_disk_size = usage.f_frsize * total_blocks
            trigger_bytes = int(total_disk_size * max_full_ratio)
            target_bytes = int(total_disk_size * target_ratio)
            target_files = int(max_files_limit * target_ratio)
        except (OSError, AttributeError, ZeroDivisionError) as e:
            logging.error(f"Error checking disk stats for {cache_dir}: {e}")
            continue

        all_files = []
        current_total_size = 0
        
        # Heavy operation: Walk the directory
        for root, _, files in os.walk(cache_dir):
            for f in files:
                if f.endswith(('.tmp', '.lock', '.etag')):
                    continue
                path = os.path.join(root, f)
                try:
                    stat = os.stat(path)
                    all_files.append([stat.st_atime, stat.st_size, path])
                    current_total_size += stat.st_size
                except OSError:
                    continue

        # 3. Cleanup to Target
        if current_total_size > trigger_bytes or len(all_files) > max_files_limit:
            all_files.sort() 
            bytes_cleared = 0
            files_removed = 0
            
            logging.info(f"Triggered cleanup: size={current_total_size}, files={len(all_files)}")

            while all_files:
                if current_total_size <= target_bytes and len(all_files) <= target_files:
                    break
                
                atime, size, path = all_files.pop(0)
                try:
                    os.remove(path)
                    etag_p = path + ".etag"
                    if os.path.exists(etag_p):
                        os.remove(etag_p)
                    
                    current_total_size -= size
                    bytes_cleared += size
                    files_removed += 1
                except OSError:
                    continue

            # 4. Prune empty directories
            for root, dirs, _ in os.walk(cache_dir, topdown=False):
                for name in dirs:
                    dir_path = os.path.join(root, name)
                    try:
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                    except OSError:
                        continue
            
            logging.info(f"Cleanup finished. Removed {files_removed} files, cleared {bytes_cleared} bytes.")

if __name__ == "__main__":
    cleanup_cache()

