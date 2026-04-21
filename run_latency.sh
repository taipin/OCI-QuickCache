#!/bin/bash

# Before running this job (get), run get_latency.py put first to create objects in object store
#
storage_type=${1:-s3cache}    # anything else will do native s3

export AWS_METADATA_SERVICE_TIMEOUT=60  # def = 1
export AWS_METADATA_SERVICE_NUM_ATTEMPTS=10  # def = 1

myconda=/fss/xh/miniconda3
source $myconda/etc/profile.d/conda.sh
conda activate QuickCache

export PYTHONPATH=${PYTHONPATH}:${PWD}    # to help relocated MLP/storage/mlpstorage/
[[ "$storage_type" == "s3cache" ]] && export export PYTHONPATH=/opt/oci-hpc/ociqc:${PYTHONPATH}

#export OCI_QC_MAX_CACHE_AGE = 360000  # TTL in seconds, invalidate cache above it
#export OCI_QC_MAX_CACHE_NO = 5000000   # Max number of files to cache
#export OCI_QC_CACHE_DIR_PREFIX="/object_store_densev4"   # default /tmp/cache_test/fs-
#export OCI_QC_SHARD_PREFIX=""   # default shard_
#export OCI_QC_SHARDS_PER_NODE=5       # default 4
#export OCI_QC_SHARD_FORM="03d"  # default "03d"
#export OCI_QC_LOG_FILE="/mnt/localdisk/xh/boto3_cache_audit.csv"  # default "boto3_cache_audit.csv"
#export OCI_QC_ERR_FILE="/mnt/localdisk/xh/boto3_cache_errors.csv"  # default "boto3_cache_errors.csv"

python get_latency.py get
