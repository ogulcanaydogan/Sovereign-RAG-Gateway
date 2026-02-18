from scripts.check_migration_v020rc1 import run_checks


def test_migration_checks_pass() -> None:
    result = run_checks()
    assert result["checks_passed"] is True
