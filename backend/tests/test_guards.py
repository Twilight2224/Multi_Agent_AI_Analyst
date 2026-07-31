from app.database import execute_readonly_sql, initialize_database
from app.sandbox import run_safe_python


def test_database_allows_select_only():
    initialize_database()
    assert "rows" in execute_readonly_sql("SELECT COUNT(*) AS count FROM customers")


def test_database_rejects_mutation():
    initialize_database()
    try:
        execute_readonly_sql("DELETE FROM customers")
    except ValueError:
        return
    raise AssertionError("mutation was accepted")


def test_sandbox_executes_safe_math_and_blocks_imports():
    assert run_safe_python("print(2 + 3)") == "5"
    try:
        run_safe_python("import os\nprint(os.getcwd())")
    except ValueError:
        return
    raise AssertionError("import was accepted")
