from app.services.inflight_guard import InflightGuard


def test_inflight_guard_global_limit_denies_after_cap() -> None:
    guard = InflightGuard(global_limit=1, tenant_default_limit=0)
    first = guard.try_acquire("tenant-a")
    second = guard.try_acquire("tenant-b")

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "global_limit"

    guard.release("tenant-a")
    third = guard.try_acquire("tenant-b")
    assert third.allowed is True


def test_inflight_guard_tenant_limit_overrides_default() -> None:
    guard = InflightGuard(
        global_limit=0,
        tenant_default_limit=2,
        tenant_limits={"tenant-a": 1},
    )
    first = guard.try_acquire("tenant-a")
    second = guard.try_acquire("tenant-a")
    third = guard.try_acquire("tenant-b")
    fourth = guard.try_acquire("tenant-b")
    fifth = guard.try_acquire("tenant-b")

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "tenant_limit"

    assert third.allowed is True
    assert fourth.allowed is True
    assert fifth.allowed is False
    assert fifth.reason == "tenant_limit"


def test_inflight_guard_disabled_without_limits() -> None:
    guard = InflightGuard(global_limit=0, tenant_default_limit=0)
    assert guard.enabled is False

    # Even while disabled, acquisition remains permissive.
    for _ in range(3):
        acquired = guard.try_acquire("tenant-a")
        assert acquired.allowed is True
        guard.release("tenant-a")
