import pytest

from pytest_diff_selector.main import run

from conftest import append_file, write_file


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
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert ret == set()


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
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

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
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)
    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_not_in_test_file(test_repo):
    write_file(
        test_repo,
        "helper.py",
        """
        def call_something():
            print('doing some changes')
    """,
    )
    test_repo.run("git add *.py")
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert "test_a.py::test_func1" in ret
    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_not_in_test_file_nested(test_repo):
    write_file(
        test_repo,
        "test_a.py",
        """
        from utils.helper import call_something

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

    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

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
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

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
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_with_no_python_file(test_repo):
    write_file(
        test_repo,
        "README.md",
        """
        # Just updating the docs
    """,
    )
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert ret == []


def test_find_change_nested_calls(test_repo):
    write_file(
        test_repo,
        "helpers.py",
        """
        def call_something():
            print('doing')
            func1()

        def func1():
            print('doing B')
    """,
    )
    test_repo.run("git add *.py")

    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert ret == set()


@pytest.mark.skip(
    reason="Not sure there's a way to detect this one, not without scanning before change took place"
)
def test_find_change_removal_from_end_of_func(test_repo):  # pragma: no cover
    write_file(
        test_repo,
        "helper.py",
        """
        def call_something():
            print('doing')
    """,
    )
    test_repo.run("git add *.py")
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert "test_a.py::test_func1" in ret
    assert "test_a.py::TestSomething::test_method" in ret


def test_find_change_in_inherited_class(test_repo):
    write_file(
        test_repo,
        "test_a.py",
        """
        from helpers import call_something

        class FatherClass:
            def father_method(self):
                call_something()

        class TestSomething(FatherClass):
            def test_method(self):
                global_var = global_var + 1
                call_something()
                self.father_method()
                assert 0/1

        def test_func1():
            call_something()

            assert False
    """,
    )
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert {"test_a.py::TestSomething::test_method"} == ret


def test_find_change_in_new_file(test_repo):
    write_file(
        test_repo,
        "test_b.py",
        """
        def test_func1():
            call_something()
            assert False
    """,
    )
    test_repo.run("git add *.py")

    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert {"test_b.py::test_func1"} == ret


def test_find_change_in_inherited_class_tests(test_repo):
    """
    * test the removal of test methods from class with __test__=False
    * test the copy of test methods based on inheritance
    """
    write_file(
        test_repo,
        "test_a.py",
        """
        from helpers import call_something

        class FatherClass:
            __test__ = False
            def father_method(self):
                call_something()
            def test_method_C(self):
                do_something_important()
                pass

        class TestSomething(FatherClass):
            def test_method(self):
                global_var = global_var + 1
                call_something()
                self.father_method()
                assert 0/1

        def test_func1():
            call_something()

            assert False
    """,
    )
    ret = run(git_diff="HEAD", root_path=test_repo.workspace)

    assert {
        "test_a.py::TestSomething::test_method_C",
        "test_a.py::TestSomething::test_method",
    } == ret
