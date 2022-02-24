from textwrap import dedent
from pathlib import Path

import pytest
from pytest_git import GitRepo


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
        from helper import call_something

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
    write_file(
        session_git_repo,
        "helper.py",
        """
        def call_something():
            print('doing')
            func1()

        def func1():
            print('doing A')
    """,
    )
    session_git_repo.run("git add *.py")
    session_git_repo.api.index.commit("Initial commit")
    yield session_git_repo


@pytest.fixture(scope="function", autouse=True)
def clear_changes(test_repo):
    test_repo.run("git stash", capture=True)
