from pathlib import Path
from textwrap import dedent

import pytest
from pytest_git import GitRepo


selector = Path(__file__).parent.parent / "pytest_diff_selector" / "main.py"


@pytest.fixture(scope="session")
def session_git_repo():
    """Session-scoped fixture to create a new git repo in a temporary workspace.

    Attributes
    ----------
    uri (str) :  Repository URI
    api (`git.Repo`) :  Git Repo object for this repository
    .. also inherits all attributes from the `workspace` fixture

    """
    with GitRepo() as repo:
        yield repo


def write_file(repo, filename, content):
    file = repo.workspace / filename
    Path(file.parent).mkdir(exist_ok=True)
    file.write_text(dedent(content))


def append_file(repo, filename, content):
    file = repo.workspace / filename
    Path(file.parent).mkdir(exist_ok=True)
    with file.open(mode="a") as f:
        f.write(dedent(content))


@pytest.fixture(scope="session")
def test_repo(session_git_repo) -> GitRepo:
    write_file(
        session_git_repo,
        "test_a.py",
        """
        from helpers import call_something

        class TestSomething:
            def test_method():
                global_var = global_var + 1
                call_something()
                assert 0/1

        def test_func1():
            call_something()

            assert False
    """,
    )
    session_git_repo.run("git add *.py")
    session_git_repo.api.index.commit("Initial commit")
    yield session_git_repo


@pytest.fixture(scope="function", autouse=True)
def clear_changes(test_repo):
    test_repo.run("git stash", capture=True)


def test_simple_scan(test_repo):
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
    ret = test_repo.run(f"python {selector} HEAD", capture=True, shell=True)

    assert "Analyzing: 100%" in ret
    assert "test_a.py::test_func1" in ret


def test_find_change_in_test_method(test_repo):
    write_file(
        test_repo,
        "test_a.py",
        """
        class TestSomething:
            def test_method():
                call_something()
                call_something_else()
                assert 0/1

        def test_func1():
            call_something()

            assert False
    """,
    )
    ret = test_repo.run(f"python {selector} HEAD", capture=True, shell=True)

    assert "Analyzing: 100%" in ret
    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_not_in_test_file(test_repo):
    write_file(
        test_repo,
        "helper.py",
        """
        def call_something():
            print('doing')
    """,
    )
    test_repo.run("git add *.py")
    ret = test_repo.run(f"python {selector} HEAD", capture=True, shell=True)

    assert "Analyzing: 100%" in ret
    assert "test_a.py::test_func1" in ret
    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_not_in_test_file_nested(test_repo):
    write_file(test_repo, "utils/__init__.py", """# just comment""")
    write_file(
        test_repo,
        "utils/helper.py",
        """
        def call_something():
            print('doing')
    """,
    )
    test_repo.run("git add utils/*.py")

    ret = test_repo.run(f"python {selector} HEAD", capture=True, shell=True)
    assert "Analyzing: 100%" in ret
    assert "test_a.py::test_func1" in ret
    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_in_test_module_scope(test_repo):
    write_file(
        test_repo,
        "test_a.py",
        """
        global_var = 20

        class TestSomething:
            def test_method():
                global_var = global_var + 1
                call_something()
                assert 0/1

        def test_func1():
            call_something()

            assert False
    """,
    )
    ret = test_repo.run(f"python {selector} HEAD", capture=True, shell=True)

    assert "Analyzing: 100%" in ret
    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_in_method_decorator(test_repo):
    write_file(
        test_repo,
        "test_a.py",
        """
        from helpers import call_something
        import pytest

        class TestSomething:
            @pytest.mark.skip
            def test_method():
                global_var = global_var + 1
                call_something()
                assert 0/1

        def test_func1():
            call_something()

            assert False
    """,
    )
    ret = test_repo.run(f"python {selector} HEAD", capture=True, shell=True)

    assert "Analyzing: 100%" in ret
    assert "test_a.py::TestSomething::test_method" in ret
