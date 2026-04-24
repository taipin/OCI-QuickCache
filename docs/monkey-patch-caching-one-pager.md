# Why Monkey Patch for Caching (One Pager)

## Context

OCI QuickCache accelerates repeated S3 `GetObject` reads by adding a local cache layer without requiring application code changes. The implementation hooks Botocore's S3 call path in `sitecustomize.py`, so existing boto3 users can benefit immediately.

## Why monkey patch here

- Zero app refactor for existing Python/boto3 workloads.
- Broad coverage: one runtime hook can protect many jobs/scripts.
- Preserves existing API surface (`GetObject`, range reads, status codes).
- Practical for mixed legacy + new workloads on shared compute clusters.

## Pros

1. Fast adoption
- No per-application integration work.
- Works for workloads that cannot be easily rewritten.

2. Operational consistency
- One centrally deployed behavior (via Ansible) across nodes.
- Unified logs and controls for cache hit/miss behavior.

3. Runtime transparency
- Applications keep using normal boto3 patterns.
- Cache path handles HIT / MISS / conditional refresh internally.

4. Better cluster economics
- Reduced repeated remote reads for hot datasets.
- Lower external dependency pressure during bursts.

## Cons and practical counterparts

1. Hidden behavior at runtime
- Risk: app owners may not realize caching is active.
- Counterpart:
- Document enablement and scope clearly.
- Keep startup banner + debug levels.
- Provide a controlled opt-out path for troubleshooting.

2. Coupling to Botocore internals
- Risk: upstream library changes may break patch assumptions.
- Counterpart:
- Pin/test supported boto3/botocore versions.
- Add smoke tests in CI for key cache flows (HIT/MISS/range).
- Keep patch surface narrow (only S3 `GetObject` interception).

3. Debug complexity
- Risk: failures can look like application bugs when they are cache-layer issues.
- Counterpart:
- Keep structured audit/error logs.
- Add explicit MISS_NO_CACHE reasons.
- Maintain debug levels and operational runbooks.

4. Cache correctness/consistency edge cases
- Risk: stale files, path/permission issues, partial writes.
- Counterpart:
- Conditional refresh checks.
- Atomic temp-to-final rename.
- Conservative fallback: serve remote if cache write path fails.

5. Multi-tenant/data-segmentation concerns
- Risk: shared cache policy can be sensitive in mixed-user clusters.
- Counterpart:
- Keep user-segmented cache layout where needed.
- Apply ACL/group policy deliberately.
- Align cleanup and shard map policies with tenancy model.

## When this approach is a good fit

- You operate many Python jobs already using boto3.
- You need cluster-wide acceleration quickly.
- You can enforce controlled runtime versions and validation.

## When a different approach may be better

- You need strict, explicit app-level control over every data path.
- Your environment forbids runtime monkey patching.
- You prefer protocol-side or gateway-side caching with no client-runtime hooks.

## Recommendation

For this package, monkey patching is a pragmatic engineering tradeoff: high leverage and low adoption friction, provided it is paired with strong observability, version discipline, and clear operator controls.
