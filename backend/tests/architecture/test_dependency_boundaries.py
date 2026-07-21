from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class _Boundary:
    roots: frozenset[str]
    allowed_prefixes: tuple[tuple[str, ...], ...]


_BOUNDARIES = (
    _Boundary(
        frozenset({"fastapi", "multipart", "starlette", "uvicorn"}),
        (("api",),),
    ),
    _Boundary(
        frozenset({"aiomysql", "alembic", "pymysql", "sqlalchemy"}),
        (("adapters", "persistence"),),
    ),
    _Boundary(
        frozenset(
            {
                "aiohttp",
                "boto3",
                "dashscope",
                "deepagents",
                "httpx",
                "langchain",
                "langchain_core",
                "langchain_openai",
                "langgraph",
                "openai",
                "ragflow_sdk",
                "redis",
                "requests",
            }
        ),
        (("adapters",),),
    ),
    _Boundary(
        frozenset({"pydantic"}),
        (("adapters", "knowledge"), ("api",), ("bootstrap",)),
    ),
    _Boundary(
        frozenset({"dotenv"}),
        (("bootstrap",),),
    ),
    _Boundary(
        frozenset({"cryptography"}),
        (("adapters",),),
    ),
    _Boundary(
        frozenset({"argon2"}),
        (("adapters", "auth"),),
    ),
)


def test_third_party_imports_stay_at_declared_boundaries() -> None:
    source_root = Path(__file__).parents[2] / "src" / "common_agent"
    violations: list[str] = []
    for source_file in source_root.rglob("*.py"):
        relative = source_file.relative_to(source_root)
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for line, module in _imports(tree):
            root = module.split(".", 1)[0]
            if root == "common_agent" or root in sys.stdlib_module_names:
                continue
            boundary = next(
                (candidate for candidate in _BOUNDARIES if root in candidate.roots),
                None,
            )
            if boundary is None:
                violations.append(f"{relative}:{line}:{module} (no declared boundary)")
                continue
            if any(relative.parts[: len(prefix)] == prefix for prefix in boundary.allowed_prefixes):
                continue
            allowed = ",".join("/".join(prefix) for prefix in boundary.allowed_prefixes)
            violations.append(f"{relative}:{line}:{module} (allowed: {allowed})")

    assert violations == []


def test_platform_layers_do_not_reach_out_to_api_or_adapters() -> None:
    source_root = Path(__file__).parents[2] / "src" / "common_agent"
    violations: list[str] = []
    for source_file in source_root.rglob("*.py"):
        relative = source_file.relative_to(source_root)
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for line, module in _imports(tree):
            if module == "common_agent.adapters" or module.startswith("common_agent.adapters."):
                if relative.parts[0] == "adapters" or relative in {
                    Path("api/app.py"),
                    Path("worker_app.py"),
                }:
                    continue
                violations.append(f"{relative}:{line}:{module} (adapter dependency points outward)")
            if module == "common_agent.api" or module.startswith("common_agent.api."):
                if relative.parts[0] in {"api", "contracts"} or relative == Path("__main__.py"):
                    continue
                violations.append(f"{relative}:{line}:{module} (API dependency points outward)")

    assert violations == []


def test_domain_depends_only_on_domain_and_standard_library() -> None:
    source_root = Path(__file__).parents[2] / "src" / "common_agent"
    domain_root = source_root / "domain"
    violations: list[str] = []
    for source_file in domain_root.rglob("*.py"):
        relative = source_file.relative_to(source_root)
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for line, module in _imports(tree):
            if module == "common_agent" or module.startswith("common_agent.domain"):
                continue
            root = module.split(".", 1)[0]
            if root in sys.stdlib_module_names:
                continue
            violations.append(f"{relative}:{line}:{module}")

    assert violations == []


def test_relative_imports_are_treated_as_platform_imports() -> None:
    tree = ast.parse("from .server import run_api\nfrom ..bootstrap import ApiSettings\n")

    assert _imports(tree) == (
        (1, "common_agent.server"),
        (2, "common_agent.bootstrap"),
    )


def test_formal_composition_uses_persistent_events_and_an_independent_worker() -> None:
    source_root = Path(__file__).parents[2] / "src" / "common_agent"
    api_source = (source_root / "api" / "app.py").read_text(encoding="utf-8")

    assert "SqlAlchemyEventJournal" in api_source
    assert "SqlAlchemyTaskQueue" in api_source
    assert ".recover_interrupted()" not in api_source
    assert importlib.util.find_spec("common_agent.worker_app") is not None
    assert importlib.util.find_spec("common_agent.worker_main") is not None


def _imports(tree: ast.AST) -> tuple[tuple[int, str], ...]:
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = f"common_agent.{module}".rstrip(".")
            imports.append((node.lineno, module))
    return tuple(imports)
