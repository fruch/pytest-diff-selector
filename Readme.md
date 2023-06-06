INSTALLING THE TOOL IN THE USER ENVIRONMENT:

pip install pytest-diff-selector

RUNNING THE TOOL(WINDOWS):

1.first option:
cd [git-project-you-want-scanning]
selector HEAD^  # scan last commit
tests/test_something.py::test_01

2.second option:
selector HEAD   # scan unstaged/uncommited work
tests/test_something.py::test_01
asciicast

INSTALLING THE DEVELOPMENT ENVIORNMENT:

pip install -e .

RUNNING THE TESTS:

cd pytest-diff-selector
pytest tests

Why
When having a long integration tests you want your CI extra smarter and don't waste time on irrelevant tests

How
Figuring out which tests are affect by specific code changes It's scanning all the project python files and build a call graph using AST, and scans this graph to find paths that are part to the change (by line numbers from the diff) that leads to a test

Currently it's only a commandline tool, but it should become a full fledged pytest plugin
