Quick latency benchmark (get_latency.py)
=====================================

This explains how to run the latency benchmark `get_latency.py` using the helper script [test/run_latency.sh](test/run_latency.sh).

Prerequisites
-------------
- Miniconda installed (the project expects `/fss/xh/miniconda3` by default). If your Miniconda is elsewhere, edit `test/run_latency.sh` and adjust `myconda`.
- Network access and credentials for the target object store. 

Create ~/.aws/config:
[default]
output = json
region = us-ashburn-1
endpoint_url = https://<Object_Storage_NAMESPACE>.compat.objectstorage.us-ashburn-1.oraclecloud.com

Create ~/.aws/credentials
[default]
aws_access_key_id = <Access_Key>
aws_secret_access_key = <Secret_Key>

Create the `QuickCache` conda environment
-----------------------------------------

```bash
myconda=/fss/xh/miniconda3
wget -q -P /tmp   https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && bash /tmp/Miniconda3-latest-Linux-x86_64.sh -b -p $myconda  && rm /tmp/Miniconda3-latest-Linux-x86_64.sh
source ${myconda}/etc/profile.d/conda.sh
conda create -n QuickCache python requests boto3
conda activate QuickCache
```

Run the benchmark
-----------------
- The helper script [test/run_latency.sh](test/run_latency.sh) activates the `QuickCache` environment and runs the `get` benchmark mode by default.
- Before running the `get` benchmark you need objects present in the target bucket. Create them with the `put` mode:

```bash
# Create objects (run from /fss/xh/test or adjust PYTHONPATH accordingly)
python get_latency.py put

# Then run the get benchmark (or use the helper script)
python get_latency.py get

# Or, using the helper script which activates conda for you:
./run_latency.sh
```

Notes
-----
- `get_latency.py` default bucket/endpoint/settings are at the top of the file. Edit those constants if you need to target a different bucket or endpoint.
- `run_latency.sh` expects Miniconda at `/fss/xh/miniconda3` and a conda env named `QuickCache`. Either create the env there or edit `run_latency.sh`.
- The script sets several `OCI_QC_*` environment variables (cache dirs, shard settings) — modify them in `run_latency.sh` when appropriate for your environment.
- Always run small tests first (reduced `TOTAL_GB` / `CONCURRENCY`) to validate connectivity and credentials.
- Check screen output for performance numbers. Check the cache files created and cache logging for HIT/MISS.

Files
-----
- Benchmark script: [test/get_latency.py](test/get_latency.py)
- Helper launcher: [test/run_latency.sh](test/run_latency.sh)
