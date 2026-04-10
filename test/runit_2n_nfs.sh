#!/bin/bash

storage_type=${1:-posix}
gpus=${2:-1}
nodes=2
pe_per_node=32
((pe_per_mpi=pe_per_node/gpus))
((total_gpus = nodes * gpus))

case "$storage_type" in
    "posix")
        extra_opts=" --data-dir /object_store_densev4-2883"
        ;;
    "s3" | "s3cache")
        extra_opts=" storage.storage_type=s3 reader.data_loader=s3 --data-dir s3://s3iad/data2"
        export AWS_METADATA_SERVICE_TIMEOUT=60  # def = 1
        export AWS_METADATA_SERVICE_NUM_ATTEMPTS=10  # def = 1
        ;;
    *)
        echo "Wrong argument $storage_type. accept null | posix | s3 | s3cache"
        exit
        ;;
esac
myconda=/fss/xh/miniconda3
source $myconda/etc/profile.d/conda.sh
conda activate mlperfs
export PATH=/usr/mpi/gcc/openmpi-4.1.9a1/bin:${PATH}

export UCX_TLS=self,sm,tcp
export UCX_NET_DEVICES=ens3
export HCOLL_MAIN_IB=$UCX_NET_DEVICES

export PYTHONPATH=${PYTHONPATH}:${PWD}    # to help relocated MLP/storage/mlpstorage/
[[ "$storage_type" == "s3cache" ]] && export export PYTHONPATH=/opt/oci-hpc/ociqc:${PYTHONPATH}

#export OCI_QC_MAX_CACHE_AGE = 360000  # TTL in seconds, invalidate cache above it
#export OCI_QC_MAX_CACHE_NO = 5000000   # Max number of files to cache
export OCI_QC_CACHE_DIR_PREFIX="/object_store_densev4"   # default /tmp/cache_test/fs-
export OCI_QC_SHARD_PREFIX=""   # default shard_
export OCI_QC_SHARDS_PER_NODE=5       # default 4
export OCI_QC_SHARD_FORM="03d"  # default "03d"
export OCI_QC_LOG_FILE="/mnt/localdisk/xh/boto3_cache_audit.csv"  # default "boto3_cache_audit.csv"
export OCI_QC_ERR_FILE="/mnt/localdisk/xh/boto3_cache_errors.csv"  # default "boto3_cache_errors.csv"

mlpstorage training run \
    --model unet3d \
    --accelerator-type h100 \
    --num-accelerators $total_gpus \
    --num-client-hosts $nodes \
    --hosts densev4-2883,densev4-4753 \
    --param dataset.num_files_train=3500 \
        reader.transfer_size=1048576 \
        reader.read_threads=32 \
        reader.prefetch_size=16 \
    $extra_opts \
    --results-dir ./results \
    --client-host-memory-in-gb 192 \
    --mpi-params "--report-bindings --bind-to hwthread --map-by ppr:${gpus}:node:pe=${pe_per_mpi} \
        -x PYTHONPATH -x PATH \
        -x UCX_TLS -x UCX_NET_DEVICES -x HCOLL_MAIN_IB \
        -x OCI_QC_CACHE_DIR_PREFIX -x OCI_QC_SHARD_PREFIX -x OCI_QC_SHARDS_PER_NODE -x OCI_QC_SHARD_FORM -x OCI_QC_LOG_FILE -x OCI_QC_ERR_FILE \
        -x CONDA_PREFIX -x CONDA_PYTHON_EXE -x CONDA_DEFAULT_ENV" \
    --exec-type mpi 2>&1 | tee LOG_2n_${gpus}_${storage_type}

#exit
#        storage.endpoint_url='https://idxzjcdglx2s.compat.objectstorage.us-ashburn-1.oraclecloud.com' \
#        storage.s3_addressing_style=path \
#    --allow-invalid-params \
#    --open \
#    --mpi-params "--report-bindings --bind-to none" \
#    --mpi-params "--report-bindings --bind-to hwthread --map-by ppr:2:node:pe=8" \
#        dataset.num_workers=0 \
