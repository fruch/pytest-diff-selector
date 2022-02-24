from pathlib import Path

from conftest import write_file

selector = Path(__file__).parent.parent / "pytest_diff_selector" / "main.py"


def test_find_change_in_test_function(test_repo):
    write_file(
        test_repo,
        "test_a.py",
        """
        def test_func1():
            call_something()
            call_something_else()

            assert True

        # comment
        def test_func2():
            assert True
    """,
    )
    ret = test_repo.run(f"python {selector} HEAD", capture=True)

    assert "Analyzing: 100%" in ret
    assert "test_a.py::test_func1" in ret
