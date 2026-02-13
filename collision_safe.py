import hashlib
import os
import requests
from urllib.parse import urlparse

def get_shard_details(url, base_dir, num_shards=5):
    # 1. Extract original filename
    parsed_url = urlparse(url)
    original_name = os.path.basename(parsed_url.path) or "data.bin"

    # 2. Generate hash for both sharding and uniqueness
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    
    # Use the first 6 characters as a unique prefix to prevent collisions
    safe_filename = f"{url_hash[:6]}_{original_name}"
    
    # 3. Calculate shard index
    shard_index = int(url_hash, 16) % num_shards
    shard_dir = os.path.join(base_dir, f"shard_{shard_index:04d}")
    
    return shard_index, shard_dir, safe_filename

def fetch_data_with_cache(url, base_dir):
    s_idx, s_dir, safe_name = get_shard_details(url, base_dir)
    file_path = os.path.join(s_dir, safe_name)
    
    # --- Cache Hit Logic ---
    if os.path.exists(file_path):
        return {"status": "HIT", "shard": s_idx, "file": safe_name}

    # --- Cache Miss Logic ---
    os.makedirs(s_dir, exist_ok=True)
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        with open(file_path, "wb") as f:
            f.write(response.content)
            
        return {"status": "MISS", "shard": s_idx, "file": safe_name}
    except Exception as e:
        return {"status": "ERROR", "shard": s_idx, "file": str(e)}

# --- Test with Potential Collisions ---
# Note: Two different URLs both ending in 'logo.png'
urls = [
    "https://pytorch.org",
    "https://www.python.org", 
    "https://pytorch.org", # Duplicate URL
]

print(f"{'STATUS':<8} | {'SHARD':<6} | {'SAFE FILENAME'}")
print("-" * 50)

for url in urls:
    res = fetch_data_with_cache(url, "./collision_safe_cache")
    print(f"{res['status']:<8} | {res['shard']:<6} | {res['file']}")

