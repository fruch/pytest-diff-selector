import os.path
import argparse
import logging
import sys
from subprocess import check_output
from collections import defaultdict
from pathlib import Path
from typing import Dict
import copy

from unidiff import PatchSet, PatchedFile, Hunk, LINE_TYPE_ADDED, LINE_TYPE_REMOVED
from pyan.analyzer import CallGraphVisitor, Flavor
from tqdm import tqdm


class CollectionVisitor(CallGraphVisitor):
    def __init__(self, *args, **kwargs):
        self.filenames_length = len(args[0])
        self.progress_bar = tqdm(desc="Analyzing", total=self.filenames_length * 2)
        super().__init__(*args, **kwargs)

    def process(self):
        self.defines_edges = defaultdict(list)
        super().process()

    def analyze_comprehension(self, *args, **kwargs):
        # since https://peps.python.org/pep-0709/ introduce in python 3.12
        # we don't comprehension in scope, so we can ignore this logic
        # locals of comprehension would be available on the parent scope
        # and that should be sufficient of this code usage
        if sys.version_info < (3, 12):
            super().analyze_comprehension(*args, **kwargs)

    def visit_FunctionDef(self, node):
        super().visit_FunctionDef(node)

        # look decorator mark them as a user of current function/method
        for n in node.decorator_list:
            self.visit(n)
            from_node = self.get_node(
                namespace=self.get_node_of_current_namespace().get_name(),
                ast_node=node,
                name=node.name,
            )
            ns = from_node.get_name()
            to_node = self.get_node(
                namespace=ns,
                name=self.last_value.name,
                ast_node=self.last_value.ast_node,
                flavor=Flavor.ATTRIBUTE,
            )
            self.add_uses_edge(from_node, to_node)
            self.last_value = None

    def process_one(self, filename):
        if self.progress_bar and self.progress_bar.disable:
            print(f"scanning: {filename}")  # pragma: no cover
        super().process_one(filename)
        if self.progress_bar:
            self.progress_bar.set_postfix_str(Path(filename).relative_to(self.root))
            self.progress_bar.update()

    def postprocess(self):
        """Finalize the analysis."""
        self.resolve_imports()
        if self.progress_bar:
            self.progress_bar.close()


def get_diff(git_repo_directory, git_selection) -> Dict[str, set]:
    """
    Get the unified diff from git, and return a mapping between file and
    line number changed
    """
    diff = check_output(
        ["git", "diff", "--no-prefix", git_selection], cwd=git_repo_directory, text=True
    )
    patch = PatchSet(diff)

    print(patch, file=sys.stderr)

    changed_lines = defaultdict(set)
    for f in patch:
        f: PatchedFile
        for hunk in f:
            hunk: Hunk
            removed = {
                line.source_line_no
                for line in hunk
                if line.line_type == LINE_TYPE_REMOVED
            }
            added = {
                line.target_line_no
                for line in hunk
                if line.line_type == LINE_TYPE_ADDED
            }
            changed_lines[f.path] = changed_lines[f.path].union(removed, added)

    return changed_lines


class AffectedTestScanner:
    """
    scan the call graph to see which test is affected by the changes
    """

    def __init__(self, graph, changed_lines_set, root_path):
        self.graph = graph
        self.changed_lines_set = changed_lines_set
        self.scanned_nodes = []
        self.current_test = None
        self.test_set = set()
        self.root_path = root_path

    def collect_tests(self) -> set:
        for key, nodes in self.graph.nodes.items():
            if key.startswith("test_"):
                self.copy_test_method_if_needed(nodes)

        for key_node, nodes in self.graph.uses_edges.items():
            if key_node.name.startswith("test_"):
                if self.check_if_test_disabled_in_scope(key_node):
                    continue
                self.current_test = key_node
                self.check_node_affected(key_node)
                self.scan_nodes(nodes)
                self.scanned_nodes.clear()

        tests = set()
        for test in self.test_set:
            relative_filename = Path(test.filename).relative_to(self.root_path)
            namespace = []
            for name in reversed(test.namespace.split(".")):
                if name == relative_filename.name.rstrip(".py"):
                    break
                namespace += [name]
            namespace = "::".join(reversed(namespace))
            namespace = f"::{namespace}" if namespace else ""
            test_full_name = f"{relative_filename}{namespace}::{test.name}"
            tests.add(test_full_name)

        return tests

    def scan_nodes(self, nodes):
        for node in nodes:
            if node.flavor in [
                Flavor.METHOD,
                Flavor.CLASSMETHOD,
                Flavor.STATICMETHOD,
                Flavor.FUNCTION,
            ]:
                if self.check_node_affected(node):
                    return True  # no point of continue if the test is already marked as affected
                if node not in self.scanned_nodes:
                    self.scanned_nodes.append(node)
                    if node in self.graph.uses_edges:
                        if self.scan_nodes(
                            self.graph.uses_edges[node]
                        ):  # pragma: no cover
                            return True  # no point of continue if the test is already marked as affected
            elif node.flavor == Flavor.IMPORTEDITEM:
                if node not in self.scanned_nodes:
                    self.scanned_nodes.append(node)
                    # since function name can be identical across module/classes, we need to
                    # cross check namespace and filename are matching
                    if self.scan_nodes(
                        [
                            n
                            for n in self.graph.nodes[node.name]
                            if node.filename == n.filename
                            and n.flavor
                            in [
                                Flavor.METHOD,
                                Flavor.CLASSMETHOD,
                                Flavor.STATICMETHOD,
                                Flavor.FUNCTION,
                            ]
                            and node.namespace in n.namespace
                        ]
                    ):
                        return True  # no point of continue if the test is already marked as affected
            elif node.flavor == Flavor.ATTRIBUTE:  # decorators or global variables
                if self.check_node_affected(node):
                    return True  # no point of continue if the test is already marked as affected
            else:
                continue
        return False

    def check_node_affected(self, node):
        if node.ast_node:
            p = str(Path(node.filename).relative_to(self.root_path))
            for line in self.changed_lines_set[p]:
                if node.ast_node.lineno <= int(line) <= node.ast_node.end_lineno:
                    self.test_set.add(self.current_test)
                    return True
        return False

    def check_if_test_disabled_in_scope(self, test_node):
        if scope := self.graph.scopes.get(test_node.namespace):
            if test_dunder := scope.defs.get("__test__"):
                return not test_dunder.ast_node.value
        return False

    def copy_test_method_if_needed(self, nodes):
        # go over test methods and lookup in the mro
        # if theres any class inheriting from the class of this method
        # and create a copy of it's usage to the inherited class
        for node in nodes:
            for klass, parents in self.graph.mro.items():
                for p in parents[1:]:
                    if node.namespace == f"{p.namespace}.{p.name}":
                        new_node = copy.deepcopy(node)
                        new_node.namespace = f"{klass.namespace}.{klass.name}"
                        new_node.filename = klass.filename
                        self.graph.uses_edges[new_node] = self.graph.uses_edges.get(
                            node, []
                        )


def run(root_path: str, git_diff: str):
    root_path = Path(os.path.abspath(root_path))
    changed_lines_set = get_diff(root_path, git_diff)
    files_changed = list(str(root_path / f) for f in changed_lines_set.keys())
    files_changed = [f for f in files_changed if f.endswith(".py")]
    if not files_changed:
        print("No python file in the change/diff")
        return []

    files = list(str(f) for f in root_path.glob("**/*.py"))
    graph = CollectionVisitor(files, str(root_path), logger=logging)

    scanner = AffectedTestScanner(graph, changed_lines_set, root_path)
    tests = scanner.collect_tests()

    return tests


def main():
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Select tests based on git diff")
    parser.add_argument(
        "git_diff", default="HEAD", type=str, help="the parameter to pass to `git diff`"
    )
    parser.add_argument(
        "--path", dest="root_path", default=".", help="the path of the git repo to scan"
    )

    args = parser.parse_args()
    tests = run(**args.__dict__)
    for test in tests:
        print(test)

    sys.exit()


if __name__ == "__main__":
    main()
