# sitecustomize.py. It integrates S3 Sharding, Atomic Streaming (TEE), LRU Background Cleanup, Conditional 304 Checks (ETag + Timestamp), and Byte-Range Request support.
import sys, os, pwd, json, hashlib, random, glob, time, csv, threading, boto3, botocore, re
from urllib.parse import urlparse
from contextlib import contextmanager
from botocore.exceptions import ClientError

# --- Configuration ---
OCI_QC_MAX_CACHE_AGE = int(os.getenv("OCI_QC_MAX_CACHE_AGE", 360000))  # TTL in seconds, invalidate cache above it
#OCI_QC_MAX_CACHE_NO = int(os.getenv("OCI_QC_MAX_CACHE_NO", 5000000))   # Max number of files to cache
#OCI_QC_MAX_CACHE_SIZE_BYTES = int(os.getenv("OCI_QC_MAX_CACHE_SIZE_BYTES", 5000 * 1024**3))
OCI_QC_CACHE_DIR_PREFIX = os.getenv("OCI_QC_CACHE_DIR_PREFIX", "/tmp/cache_test/fs-")
OCI_QC_SHARD_PREFIX = os.getenv("OCI_QC_SHARD_PREFIX", "shard_")
#OCI_QC_NUM_SHARDS = int(os.getenv("OCI_QC_NUM_SHARDS", 4))   # Calculated, not used anymore
OCI_QC_SHARDS_PER_NODE = int(os.getenv("OCI_QC_SHARDS_PER_NODE", 4))
OCI_QC_SHARD_FORM = os.getenv("OCI_QC_SHARD_FORM", "03d")
OCI_QC_LOG_FILE = os.getenv("OCI_QC_LOG_FILE", "boto3_cache_audit.csv")
OCI_QC_ERR_FILE = os.getenv("OCI_QC_ERR_FILE", "boto3_cache_errors.csv")
OCI_QC_STOP_ON_SHARD_FAILURE = os.getenv("OCI_QC_STOP_ON_SHARD_FAILURE", False)
OCI_QC_SHARD_MAP_FILE = os.getenv("OCI_QC_SHARD_MAP_FILE", "oci_qc_shard_map.json")
OCI_QC_SHARD_MAP_REFRESH_INTERVAL = int(os.getenv("OCI_QC_SHARD_MAP_REFRESH_INTERVAL", 600)) # time interval in seconds to refresh shard map
OCI_QC_LAST_CHECK_TIME = 0  # In-memory global for current process
OCI_FS_PATTERN = f"{OCI_QC_CACHE_DIR_PREFIX}*"  # search pattern for mount points example /object_store_
OCI_QC_ROOT_DEV_ID = os.stat('/').st_dev   # will check against to avoid root device if not /tmp
#USE_DIRECT_IO = True   # an experimental parameter to control cache read
USE_DIRECT_IO = False
USER_NAME = pwd.getpwuid(os.getuid()).pw_name   # for cache subdir

#print(f"xh envs OCI_QC_SHARD_PREFIX = {OCI_QC_SHARD_PREFIX}, OCI_QC_LOG_FILE = {OCI_QC_LOG_FILE}")
# --- Locking Mechanism ---
try:
    import fcntl
except ImportError:
    fcntl = None

@contextmanager
def lock_file(f):
    """Provides thread and process safe locking for an open file."""
    if fcntl:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    else:
        yield

@contextmanager
def lock_shard_map():
    """Queues up processes using a dedicated lock file (avoids truncation bugs)."""
    lock_path = OCI_QC_SHARD_MAP_FILE + ".lock"
    # Use 'a' (append) so we don't truncate the lock file itself
    with open(lock_path, 'a') as f:
        if fcntl:
            try:
                # LOCK_EX without LOCK_NB means "wait in line"
                fcntl.flock(f, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        else:
            yield

def is_valid_mount(path):
    """
    Vets a mount point.
    Allows anything in /tmp/ (for testing).
    Otherwise, requires a separate physical device (for production).
    """
    try:
        # Normalize path to handle trailing slashes
        norm_path = os.path.normpath(path)

        # 1. THE EXCEPTION: If it's in /tmp, allow it immediately
        if norm_path.startswith('/tmp/'):
            return os.path.exists(norm_path)

        # 2. THE PRODUCTION RULE: Must be a separate device from root
        return os.stat(norm_path).st_dev != OCI_QC_ROOT_DEV_ID

    except (OSError, PermissionError):
        return False

def handle_shard_failure(message):
    if OCI_QC_STOP_ON_SHARD_FAILURE:
        print(f"CRITICAL: {message} Exiting...")
        sys.exit(1)
    else:
        print(f"CRITICAL: {message} Keep going without OCI_QC...")

    return None

# --- Initialize shard map
def initialize_sharding():
    """Discovers mounts and returns shard map. Returns None on failure to bypass cache."""
    try:
        # Fast path: if map exists, read it without a lock
        if os.path.exists(OCI_QC_SHARD_MAP_FILE):
            with open(OCI_QC_SHARD_MAP_FILE, 'r') as f:
                return json.load(f)

        # Everything else goes inside the lock
        with lock_shard_map():
            # Double check existence after acquiring lock
            if os.path.exists(OCI_QC_SHARD_MAP_FILE):
                with open(OCI_QC_SHARD_MAP_FILE, 'r') as f:
                    return json.load(f)

            # 1. Discover and Filter
            mount_points = sorted(glob.glob(OCI_FS_PATTERN))
            mount_points = [p for p in mount_points if is_valid_mount(p)]

            if not mount_points:
                return handle_shard_failure("No valid mounts found.")

            # 2. Map Generation
            N = len(mount_points)
            total_shards = N * OCI_QC_SHARDS_PER_NODE
            shard_map = {str(i): mount_points[i % N] for i in range(total_shards)}

            # 3. Atomic Persistence
            tmp_file = OCI_QC_SHARD_MAP_FILE + ".tmp"
            with open(tmp_file, 'w') as f:
                json.dump(shard_map, f)
            os.rename(tmp_file, OCI_QC_SHARD_MAP_FILE)
            
            return shard_map

    except Exception as e:
        # Catch locking errors, JSON errors, or permission errors
        print(f"CRITICAL: Sharding initialization failed: {e}. Bypassing cache.")
        return None


# Load map into memory once at startup and hard-set OCI_QC_SHARD_MAP to 1 to avoid divide by zero
OCI_QC_SHARD_MAP = initialize_sharding()
OCI_QC_NUM_SHARDS = len(OCI_QC_SHARD_MAP) if OCI_QC_SHARD_MAP else 1

# --- Utility Functions ---
def get_shard_details(bucket, key, region=None):
    global OCI_QC_LAST_CHECK_TIME, OCI_QC_SHARD_MAP, OCI_QC_NUM_SHARDS
    
    now = time.time()
    # Check if we need to refresh (every 10 mins)
    if (now - OCI_QC_LAST_CHECK_TIME) > OCI_QC_SHARD_MAP_REFRESH_INTERVAL:
        OCI_QC_SHARD_MAP = initialize_sharding()
        OCI_QC_NUM_SHARDS = len(OCI_QC_SHARD_MAP)
        OCI_QC_LAST_CHECK_TIME = now

    if OCI_QC_SHARD_MAP is None:
        # Return dummy values that signal 'is_available = False'
        return "", "", 0, False

    # Standard Hashing Logic
    resource_path = f"s3://{bucket}/{key}"
    url_hash = hashlib.md5(resource_path.encode('utf-8')).hexdigest()
    
    shard_idx = int(url_hash, 16) % OCI_QC_NUM_SHARDS
    mount_path = OCI_QC_SHARD_MAP[str(shard_idx)]
    
    # Path construction
    shard_name = f"{OCI_QC_SHARD_PREFIX}{shard_idx:{OCI_QC_SHARD_FORM}}"
    shard_dir = os.path.join(mount_path, f"OCI_QC_Cache/{USER_NAME}", shard_name)
    region = region or "unknown-region"
    key_dir = os.path.dirname(key).lstrip('/')
    key_file = os.path.basename(key) or 'object.bin'
    # Check if the disk is actually mounted
    is_available = is_valid_mount(mount_path)

    full_path = os.path.join(
        shard_dir,
        region,
        bucket,
        key_dir,
        key_file
    )

    return full_path, url_hash, shard_idx, is_available

def log_event(resource, reason, file_path, url_hash, shard_idx):
    file_exists = os.path.isfile(OCI_QC_LOG_FILE)
    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    with open(OCI_QC_LOG_FILE, mode='a', newline='') as f:
        with lock_file(f):
            writer = csv.writer(f, lineterminator='\n')
            if not file_exists:
                writer.writerow(['timestamp', 'resource', 'reason', 'hash', 'shard', 'size_bytes', 'mtime', 'atime'])
            writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), resource, reason, url_hash, shard_idx, size, time.time(), time.time()])

def log_error_event(resource, reason, file_path, url_hash, shard_idx):
    """Separate logging for MISS_NO_CACHE and related errors (controlled by OCI_QC_ERR_FILE)."""
    file_exists = os.path.isfile(OCI_QC_ERR_FILE)
    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    try:
        with open(OCI_QC_ERR_FILE, mode='a', newline='') as f:
            with lock_file(f):
                writer = csv.writer(f, lineterminator='\n')
                if not file_exists:
                    writer.writerow(['timestamp', 'resource', 'reason', 'hash', 'shard', 'size_bytes', 'mtime', 'atime'])
                writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), resource, reason, url_hash, shard_idx, size, time.time(), time.time()])
    except Exception:
        # swallow errors to avoid affecting normal flow
        pass

def parse_range(range_str, total_size):
    if not range_str: return 0, total_size - 1
    match = re.match(r'bytes=(\d+)-(\d*)', range_str)
    if not match: return 0, total_size - 1
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else total_size - 1
    return start, min(end, total_size - 1)

#def background_worker():
#    while True:
#        try: cleanup_cache()
#        except: pass
#        time.sleep(10)
#threading.Thread(target=background_worker, daemon=True).start()

#xh adding direct io
class DirectIOFile:
    def __init__(self, path):
        # Open with O_DIRECT for PCIe Gen 4 speeds
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
        self.pos = 0

    def read(self, amt=None):
        if amt is None or amt < 0:
            amt = os.fstat(self.fd).st_size - self.pos

        # O_DIRECT requires 4096-byte alignment for both buffer and offset
        align = 4096
        offset = (self.pos // align) * align
        shift = self.pos % align
        read_amt = ((amt + shift + align - 1) // align) * align

        # Seek and read at the aligned boundary
        os.lseek(self.fd, offset, os.SEEK_SET)
        chunk = os.read(self.fd, read_amt)

        data = chunk[shift : shift + amt]
        self.pos += len(data)
        return data

    def seek(self, offset):
        self.pos = offset

    def close(self):
        if self.fd:
            os.close(self.fd)
            self.fd = None

# --- Classes ---
class MockStreamingBody:
    def __init__(self, stream_source, from_cache=False, file_path=None, range_start=0, range_end=None):
        self._raw_stream = stream_source
        self.from_cache = from_cache
        self._file_path = file_path
        self._range_start = range_start
        self._range_end = range_end
        self._amount_read = 0
        self._is_done = False

    def read(self, amt=None):
        if self._range_end is not None:
            remaining = (self._range_end - self._range_start + 1) - self._amount_read
            if remaining <= 0: return b""
            if amt is None or amt > remaining: amt = remaining

        data = self._raw_stream.read(amt)
        self._amount_read += len(data)
        if (amt is None or not data) and not self._is_done:
            self._finalize()
        return data

    def _finalize(self):
        self._is_done = True
        self.close()

    def close(self):
        if self._raw_stream and hasattr(self._raw_stream, 'close'):
            self._raw_stream.close()
        self._raw_stream = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def iter_chunks(self, chunk_size=1024):
        while True:
            chunk = self.read(chunk_size)
            if not chunk: break
            yield chunk

# --- Monkey Patching ---
_original_make_api_call = botocore.client.BaseClient._make_api_call

def patched_make_api_call(self, operation_name, kwarg):
    #print(f"xh intercepted, operation_name = {operation_name}, kwarg = {kwarg}")

    # If sharding failed to init, bypass cache entirely
    if not OCI_QC_SHARD_MAP:
        return _original_make_api_call(self, operation_name, kwarg)

    if operation_name == 'GetObject' and self.meta.service_model.service_name == 's3':
        bucket, key = kwarg.get('Bucket'), kwarg.get('Key')
        user_range = kwarg.get('Range')
        #print(f"xh user_range = {user_range}, kwarg = {kwarg}")
        resource = f"s3://{bucket}/{key}"
        region = getattr(self.meta, "region_name", None)

        file_path, url_hash, shard_idx, is_available = get_shard_details(bucket, key, region)
        etag_path = os.path.join(os.path.dirname(file_path), "." + os.path.basename(file_path) + ".etag")
        if not is_available:
            log_error_event(f"s3://{bucket}/{key}", "MISS_MOUNT_NA", "", url_hash, shard_idx)
            return _original_make_api_call(self, operation_name, kwarg)

        # Path Length Validation & Logging
        # Linux limits: 255 for filename, 4096 for full path
        path_limit = 4096
        file_limit = 255
        base_name = os.path.basename(file_path)

        path_errors = []
        if len(file_path) > path_limit:
            path_errors.append(f"PATH_LIMIT({len(file_path)})")
        if len(base_name) > file_limit:
            path_errors.append(f"FILE_LIMIT({len(base_name)})")

        if path_errors:
            reason = f"MISS_PATH_LIMIT:{path_errors}"
            log_error_event(f"s3://{bucket}/{key}", reason, "", url_hash, shard_idx)

            # Bypass cache for invalid paths to avoid OSError
            return _original_make_api_call(self, operation_name, kwarg)

        is_fresh = os.path.exists(file_path) and (time.time() - os.path.getmtime(file_path) <= OCI_QC_MAX_CACHE_AGE)
        #print(f"key = {key}, is_fresh = {is_fresh}")

        # 1. DIRECT HIT (Fresh file)
        if is_fresh:
            total_size = os.path.getsize(file_path)
            if USE_DIRECT_IO:
                f = DirectIOFile(file_path)
            else:
                f = open(file_path, 'rb')
                #print(f"key = {key}, is_fresh = {is_fresh} HIT")
            if user_range:
                log_event(resource, "HIT_RANGE", file_path, url_hash, shard_idx)
                start, end = parse_range(user_range, total_size)
                if start > 0: f.seek(start)
                return {
                    'Body': MockStreamingBody(f, from_cache=True, file_path=file_path, range_start=start, range_end=end),
                    'ContentLength': (end - start + 1),
                    'ResponseMetadata': {'HTTPStatusCode': 206}
                }
            else:
                log_event(resource, "HIT", file_path, url_hash, shard_idx)
                return {
                    'Body': MockStreamingBody(f, from_cache=True),  # can add back file_path=file_path, range_start=start, range_end=end if needed
                    'ContentLength': total_size,
                    'ResponseMetadata': {'HTTPStatusCode': 200}
                }

        # 2. EXPIRED -> Conditional 304 Not Modified Check
        if os.path.exists(file_path):
            check_kwargs = kwarg.copy()
            check_kwargs.pop('Range', None)
            check_kwargs['IfModifiedSince'] = time.ctime(os.path.getmtime(file_path))
            if os.path.exists(etag_path):
                with open(etag_path, 'r') as ef: check_kwargs['IfNoneMatch'] = ef.read().strip()

            try:
                _original_make_api_call(self, operation_name, check_kwargs)
            except ClientError as e:
                if e.response['ResponseMetadata']['HTTPStatusCode'] == 304:
                    # REFRESH AND SERVE (No recursion, preventing double logs)
                    os.utime(file_path, None)
                    log_event(resource, "NOT_MODIFIED", file_path, url_hash, shard_idx)

                    total_size = os.path.getsize(file_path)
                    f = DirectIOFile(file_path) if USE_DIRECT_IO else open(file_path, 'rb')
                    
                    if user_range:
                        start, end = parse_range(user_range, total_size)
                        if start > 0: f.seek(start)
                        return {
                            'Body': MockStreamingBody(f, from_cache=True, file_path=file_path, range_start=start, range_end=end),
                            'ContentLength': (end - start + 1),
                            'ResponseMetadata': {'HTTPStatusCode': 206}
                        }
                    else:
                        return {
                            'Body': MockStreamingBody(f, from_cache=True),
                            'ContentLength': total_size,
                            'ResponseMetadata': {'HTTPStatusCode': 200}
                        }
                raise e # If it's not a 304, something else went wrong or it's a 404

        # 3. MISS (Full download)
        network_kwargs = kwarg.copy()
        network_kwargs.pop('Range', None)
        response = _original_make_api_call(self, operation_name, network_kwargs)
        if response.get('ResponseMetadata', {}).get('HTTPStatusCode') in [200, 206]:
            # Note: We only cache if it's a full 200 response to avoid partial shards
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                #print(f"key = {key}, is_fresh = {is_fresh} MISS file_path = {file_path}  dirname(file_path) = {os.path.dirname(file_path)}")
                # Try to prepare cache directory and temp file. If we cannot create them
                # (permissions, broken links, etc.), do not attempt to cache — just
                # return the network response and log a concise reason.
                try:
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                except OSError as e:
                    reason = f"MISS_NO_CACHE:mkdir_failed:{e.__class__.__name__}:{e}"
                    try:
                        log_error_event(resource, reason, file_path, url_hash, shard_idx)
                    except Exception:
                        pass
                    return response

                temp_path = f"{file_path}.{random.getrandbits(64):016x}.tmp"
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        # If we cannot remove an existing temp, give up caching
                        reason = "MISS_NO_CACHE:temp_remove_failed"
                        try:
                            log_error_event(resource, reason, file_path, url_hash, shard_idx)
                        except Exception:
                            pass
                        return response

                # Quick writable check: try to create the temp file to ensure
                # we have permission to write into the target directory.
                try:
                    open(temp_path, 'wb').close()
                except OSError as e:
                    reason = f"MISS_NO_CACHE:temp_create_failed:{e.__class__.__name__}:{e}"
                    try:
                        log_error_event(resource, reason, file_path, url_hash, shard_idx)
                    except Exception:
                        pass
                    return response


                etag = response.get('ETag') or response.get('ResponseMetadata', {}).get('HTTPHeaders', {}).get('etag')

                class TEEBody(MockStreamingBody):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        # Open once at start
                        self.ft = open(temp_path, 'wb')

                    def read(self, amt=None):
                        data = self._raw_stream.read(amt)
                        if data:
                            try:
                                self.ft.write(data)
                                self.ft.flush() # Ensure it hits disk immediately
                            except OSError:
                                # If writing fails mid-stream, stop trying to cache
                                try:
                                    self.ft.close()
                                except Exception:
                                    pass
                                # Remove incomplete temp file if possible
                                try:
                                    if os.path.exists(temp_path): os.remove(temp_path)
                                except Exception:
                                    pass

                        # Check for end of stream
                        if (amt is None or not data) and not self._is_done:
                            self._finalize()
                        return data

                    def _finalize(self):
                        if not self._is_done:
                            try:
                                self.ft.close() # Close the handle before renaming
                            except Exception:
                                pass
                            if os.path.exists(temp_path):
                                try:
                                    os.rename(temp_path, file_path)
                                    if etag:
                                        with open(etag_path, 'w') as ef: ef.write(etag)
                                    log_event(resource, "MISS", file_path, url_hash, shard_idx)
                                except OSError:
                                    # If rename fails, ensure we don't leave temp files
                                    try:
                                        if os.path.exists(temp_path): os.remove(temp_path)
                                    except Exception:
                                        pass
                            super()._finalize()

                response['Body'] = TEEBody(response['Body'], from_cache=False, file_path=file_path)
            return response

    return _original_make_api_call(self, operation_name, kwarg)

botocore.client.BaseClient._make_api_call = patched_make_api_call
print("!!! SITECUSTOMIZE: Universal S3 Cache (Range + 304 + LRU) Active !!!")
