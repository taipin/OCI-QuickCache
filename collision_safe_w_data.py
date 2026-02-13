import hashlib
import os
import requests
from urllib.parse import urlparse

def get_shard_details(url, base_dir, num_shards=5):
    parsed_url = urlparse(url)
    original_name = os.path.basename(parsed_url.path) or "data.bin"
    
    # 1. Generate unique hash for sharding and uniqueness
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    
    # 2. Collision-safe filename (Hash Prefix + Original Name)
    safe_filename = f"{url_hash[:6]}_{original_name}"
    
    # 3. Determine Shard Directory
    shard_index = int(url_hash, 16) % num_shards
    shard_dir = os.path.join(base_dir, f"shard_{shard_index:04d}")
    
    return shard_index, shard_dir, safe_filename

def fetch_data_with_cache(url, base_dir):
    s_idx, s_dir, safe_name = get_shard_details(url, base_dir)
    file_path = os.path.join(s_dir, safe_name)
    
    # --- CACHE HIT ---
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            data = f.read()
        return data, "HIT", s_idx, safe_name

    # --- CACHE MISS ---
    os.makedirs(s_dir, exist_ok=True)
    try:
        # Download from source
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.content
        
        # Save to shard for future HITs
        with open(file_path, "wb") as f:
            f.write(data)
            
        return data, "MISS", s_idx, safe_name
    except Exception as e:
        return None, f"ERROR: {e}", s_idx, safe_name

# --- Test Example with Multiple URLs ---
if __name__ == "__main__":
    BASE_CACHE = "./collision_safe_cache"
    urls = [
        "https://pytorch.org",
        "https://www.python.org",
        "https://pytorch.org", # Duplicate for HIT
        "https://objectstorage.us-ashburn-1.oraclecloud.com/p/VBnsQ8lIO44K5pAzIK7nUpKjN5Znj-jmMM07Z7OrfdPOqfWIilqdOrb4IwQcxPcf/n/idxzjcdglx2s/b/s3iad/o/Amber23.pdf",
        "https://objectstorage.us-ashburn-1.oraclecloud.com/p/2g0lIzGR7j1z4wkCoVWRuT6NbL2YWlDRo7peS21PT-jmwzoC6vVY-l_Z_NQcwJd3/n/idxzjcdglx2s/b/s3iad/o/LBNL_Part2.pptx",
        "https://objectstorage.us-ashburn-1.oraclecloud.com/p/2g0lIzGR7j1z4wkCoVWRuT6NbL2YWlDRo7peS21PT-jmwzoC6vVY-l_Z_NQcwJd3/n/idxzjcdglx2s/b/s3iad/o/LBNL_Part2.pptx"
    ]

    print(f"{'STATUS':<8} | {'SHARD':<6} | {'BYTES':<10} | {'FILENAME'}")
    print("-" * 60)

    for url in urls:
        data, status, shard_idx, filename = fetch_data_with_cache(url, BASE_CACHE)
        
        # data is the actual binary content (e.g., image bytes)
        data_len = len(data) if data else 0
        
        print(f"{status:<8} | {shard_idx:<6} | {data_len:<10} | {filename}")

