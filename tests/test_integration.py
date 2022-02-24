from pathlib import Path

from conftest import append_file

selector = Path(__file__).parent.parent / "pytest_diff_selector" / "main.py"


def test_simple_scan_from_commandline(test_repo):
    append_file(
        test_repo,
        "test_a.py",
        """
        # comment
        def test_func2():
            assert True
    """,
    )
    ret = test_repo.run(f"python {selector} HEAD", capture=True)

    assert "Analyzing: 100%" in ret
