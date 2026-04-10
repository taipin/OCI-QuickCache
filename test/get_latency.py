import boto3
import time
import statistics
import os
import sys
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from botocore.config import Config

# --- OCI COMPATIBILITY FIX ---
os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] = "when_required"
os.environ["AWS_RESPONSE_CHECKSUM_VALIDATION"] = "when_required"

# --- CONFIGURATION ---
#BUCKET = "s3iad"
#ENDPOINT_URL = "https://idxzjcdglx2s.compat.objectstorage.us-ashburn-1.oraclecloud.com"
BUCKET = "xhosaka"
ENDPOINT_URL = "https://idxzjcdglx2s.compat.objectstorage.ap-osaka-1.oraclecloud.com"
PREFIX = "xh_test_pool"
CONCURRENCY = 32 #4 #32 
TOTAL_GB = 1
FILE_SIZE_KB = 128 #8192 #128
CSV_FILENAME = "oci_benchmark_results.csv"

def get_client():
    """Each process needs its own Boto3 client."""
    config = Config(
        max_pool_connections=5, # Small pool since it's 1 client per process
        s3={'addressing_style': 'path'}
    )
    return boto3.client('s3', endpoint_url=ENDPOINT_URL, config=config)

def get_file_keys():
    num_files = int((TOTAL_GB * 1024 * 1024) / FILE_SIZE_KB)
    return [f"{PREFIX}/file_{i}.bin" for i in range(num_files)]

# --- WORKER FUNCTIONS ---

def worker_put(key):
    s3 = get_client()
    data = b"x" * (FILE_SIZE_KB * 1024)
    try:
        s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentLength=len(data))
        return True
    except Exception as e:
        return str(e)

def worker_get(key):
    s3 = get_client()
    # Start timer INSIDE the worker to measure actual I/O, not scheduling delay
    t0 = time.perf_counter()
    try:
        # Note: Boto3 get_object is a FULL request. 
        # For a Range request, use: s3.get_object(..., Range='bytes=0-100')
        resp = s3.get_object(Bucket=BUCKET, Key=key)

        # Check HTTP Status (200 for full, 206 for range)
        status = resp['ResponseMetadata']['HTTPStatusCode']
        if status not in [200, 206]:
            return {"success": False, "error": f"Bad Status: {status}"}
        
        # Measure TTFB by reading 1 byte
        first_byte = resp['Body'].read(1)
        ttfb = (time.perf_counter() - t0) * 1000
        
        # Drain the rest of the file
        remaining = resp['Body'].read()
        duration = time.perf_counter() - t0
        size = len(remaining) + len(first_byte)
        expected_size = FILE_SIZE_KB * 1024
        if size != expected_size:
            return {"success": False, "error": f"Size Mismatch (actual/expected): {size}/{expected_size}"}
        
        return {"success": True, "ttfb": ttfb, "bytes": size, "duration": duration}
    except Exception as e:
        return {"success": False, "error": str(e)}

def worker_cleanup(keys_chunk):
    s3 = get_client()
    try:
        # OCI requires MD5 for batch deletes. 
        # Boto3 usually handles this, but if it fails, delete_object loop is safer.
        s3.delete_objects(Bucket=BUCKET, Delete={'Objects': [{'Key': k} for k in keys_chunk]})
        return len(keys_chunk)
    except:
        # Fallback to individual deletes if Batch fails
        count = 0
        for k in keys_chunk:
            s3.delete_object(Bucket=BUCKET, Key=k)
            count += 1
        return count

# --- MAIN EXECUTION MODES ---

def run_put(keys):
    print(f"--- PUT: Generating {len(keys)} files via {CONCURRENCY} Processes ---")
    with ProcessPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(worker_put, k) for k in keys]
        for i, f in enumerate(as_completed(futures)):
            if (i + 1) % 100 == 0: print(f"Uploaded {i+1}/{len(keys)}")

def run_get(keys):
    print(f"--- GET: Benchmarking {len(keys)} files via {CONCURRENCY} Processes ---")
    results = []
    errors = []
    start_wall = time.perf_counter()

    with ProcessPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(worker_get, k) for k in keys]
        for f in as_completed(futures):
            res = f.result()
            if res["success"]:
                results.append(res)
            else:
                errors.append(res["error"])

    wall_duration = time.perf_counter() - start_wall
    total_requested = len(keys)
    total_success = len(results)
    print(f"\n--- Integrity Check ---")
    print(f"Requested: {total_requested} | Succeeded: {total_success} | Failed: {len(errors)}")

    if errors:
        print(f"Sample Errors: {errors[:3]}") # Show first few errors

    if total_success < total_requested:
        print(f"WARNING: Benchmark incomplete! Only {total_success/total_requested:.1%} successful.")

    if not results: return

    ttfbs = [r['ttfb'] for r in results]
    total_mb = sum(r['bytes'] for r in results) / (1024 * 1024)
    agg_throughput = total_mb / wall_duration

    stats = {
        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "Size_KB": FILE_SIZE_KB,
        "Avg_TTFB_ms": round(statistics.mean(ttfbs), 2),
        "P99_TTFB_ms": round(statistics.quantiles(ttfbs, n=100)[98], 2),
        "Agg_Throughput_MBs": round(agg_throughput, 2)
    }

    print(f"Results: {stats['Agg_Throughput_MBs']} MB/s | Avg TTFB: {stats['Avg_TTFB_ms']}ms")
    
    file_exists = os.path.isfile(CSV_FILENAME) and os.path.getsize(CSV_FILENAME) > 0
    with open(CSV_FILENAME, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=stats.keys())
        if not file_exists: writer.writeheader()
        writer.writerow(stats)

def run_cleanup(keys):
    print(f"--- CLEANUP: Deleting {len(keys)} files ---")
    # Batch delete 1000 at a time
    chunks = [keys[i:i + 1000] for i in range(0, len(keys), 1000)]
    with ProcessPoolExecutor(max_workers=CONCURRENCY) as executor:
        list(executor.map(worker_cleanup, chunks))
    print("Cleanup Complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bmk_final.py [put|get|cleanup]")
        sys.exit(1)

    mode = sys.argv[1].lower()
    keys = get_file_keys()

    if mode == "put": run_put(keys)
    elif mode == "get": run_get(keys)
    elif mode == "cleanup": run_cleanup(keys)

