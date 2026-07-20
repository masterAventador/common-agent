from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKEND_SOURCE = REPOSITORY_ROOT / "backend" / "src"
FRONTEND_SOURCE = REPOSITORY_ROOT / "frontend" / "src"

FOCUSED_LINE_BUDGETS = {
    "backend/src/common_agent/conversations/service.py": 220,
    "backend/src/common_agent/application/workflow_service.py": 220,
    "backend/src/common_agent/api/routers/conversations.py": 240,
    "backend/src/common_agent/api/routers/workflows.py": 240,
    "backend/src/common_agent/api/routers/workflow_runs.py": 240,
    "frontend/src/features/chat/ChatPage.tsx": 180,
    "frontend/src/features/workflows/WorkflowsPage.tsx": 180,
}

IMPLEMENTATION_MODULES = (
    "common_agent.conversations.persistence",
    "common_agent.conversations.projection",
    "common_agent.conversations.runtime",
    "common_agent.application.workflow_catalog",
    "common_agent.application.workflow_run_projection",
    "common_agent.application.workflow_runs",
)
FACADE_MODULES = {
    "common_agent.conversations.service",
    "common_agent.application.workflow_service",
}
SPLIT_BACKEND_MODULES = (
    set(IMPLEMENTATION_MODULES)
    | FACADE_MODULES
    | {
        "common_agent.conversations.contracts",
        "common_agent.application.workflow_contracts",
    }
)
IMPORT_PATTERN = re.compile(r"\bfrom\s+[\"']([^\"']+)[\"']|\bimport\s+[\"']([^\"']+)[\"']")


@pytest.mark.parametrize(("relative_path", "maximum"), FOCUSED_LINE_BUDGETS.items())
def test_orchestration_files_stay_within_responsibility_budget(
    relative_path: str,
    maximum: int,
) -> None:
    path = REPOSITORY_ROOT / relative_path

    line_count = len(path.read_text(encoding="utf-8").splitlines())

    assert line_count <= maximum, f"{relative_path} has {line_count} lines; budget is {maximum}"


def test_backend_implementation_modules_do_not_import_service_facades() -> None:
    violations: list[str] = []
    for module_name in IMPLEMENTATION_MODULES:
        path = BACKEND_SOURCE / Path(*module_name.split(".")).with_suffix(".py")
        if not path.exists():
            continue
        imports = _python_imports(path)
        forbidden = sorted(imports & FACADE_MODULES)
        if forbidden:
            violations.append(f"{path.relative_to(REPOSITORY_ROOT)} -> {', '.join(forbidden)}")

    assert not violations, "实现模块不得反向导入服务门面:\n" + "\n".join(violations)


def test_frontend_features_do_not_import_other_feature_private_modules() -> None:
    violations: list[str] = []
    features_root = FRONTEND_SOURCE / "features"
    for path in features_root.glob("*/*.[tj]s*"):
        feature_name = path.relative_to(features_root).parts[0]
        for specifier in _typescript_imports(path):
            if not specifier.startswith("."):
                continue
            resolved = (path.parent / specifier).resolve()
            try:
                relative = resolved.relative_to(features_root.resolve())
            except ValueError:
                continue
            target_feature = relative.parts[0]
            if target_feature != feature_name and relative.name not in {
                "index",
                "index.ts",
                "index.tsx",
            }:
                violations.append(
                    f"{path.relative_to(REPOSITORY_ROOT)} -> {specifier} ({target_feature})"
                )

    assert not violations, "Feature 之间只能依赖对方公开 index:\n" + "\n".join(violations)


def test_frontend_implementation_modules_do_not_import_page_containers() -> None:
    violations: list[str] = []
    for feature, container in (("chat", "ChatPage"), ("workflows", "WorkflowsPage")):
        feature_root = FRONTEND_SOURCE / "features" / feature
        for path in feature_root.glob("*.[tj]s*"):
            if path.stem == container or path.name.endswith(".test.tsx"):
                continue
            for specifier in _typescript_imports(path):
                if specifier.removesuffix(".tsx").endswith(f"/{container}"):
                    violations.append(f"{path.relative_to(REPOSITORY_ROOT)} -> {specifier}")

    assert not violations, "Feature 实现不得反向依赖页面容器:\n" + "\n".join(violations)


def test_split_backend_modules_have_no_circular_dependencies() -> None:
    graph: dict[str, set[str]] = {}
    for module_name in SPLIT_BACKEND_MODULES:
        path = BACKEND_SOURCE / Path(*module_name.split(".")).with_suffix(".py")
        graph[module_name] = _python_imports(path) & SPLIT_BACKEND_MODULES

    _assert_acyclic(graph)


@pytest.mark.parametrize("feature", ("chat", "workflows"))
def test_split_frontend_features_have_no_circular_dependencies(feature: str) -> None:
    feature_root = FRONTEND_SOURCE / "features" / feature
    paths = tuple(
        path
        for path in (*feature_root.glob("*.ts"), *feature_root.glob("*.tsx"))
        if ".test." not in path.name
    )
    module_by_path = {path.resolve(): path.stem for path in paths}
    graph: dict[str, set[str]] = {path.stem: set() for path in paths}
    for path in paths:
        for specifier in _typescript_imports(path):
            if not specifier.startswith("."):
                continue
            target = (path.parent / specifier).resolve()
            resolved = next(
                (
                    candidate
                    for candidate in (target, target.with_suffix(".ts"), target.with_suffix(".tsx"))
                    if candidate in module_by_path
                ),
                None,
            )
            if resolved is not None:
                graph[path.stem].add(module_by_path[resolved])

    _assert_acyclic(graph)


def _python_imports(path: Path) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            imports.add(node.module)
    return imports


def _typescript_imports(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    return tuple(match.group(1) or match.group(2) for match in IMPORT_PATTERN.finditer(source))


def _assert_acyclic(graph: dict[str, set[str]]) -> None:
    visited: set[str] = set()
    active: list[str] = []

    def visit(module_name: str) -> None:
        if module_name in active:
            cycle_start = active.index(module_name)
            cycle = " -> ".join((*active[cycle_start:], module_name))
            pytest.fail(f"发现循环依赖: {cycle}")
        if module_name in visited:
            return
        active.append(module_name)
        for dependency in sorted(graph[module_name]):
            visit(dependency)
        active.pop()
        visited.add(module_name)

    for module_name in sorted(graph):
        visit(module_name)
