import ast
from pathlib import Path

FORBIDDEN_FRAMEWORKS = {"aiogram", "fastapi", "sqlalchemy", "celery", "redis", "openai"}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_domain_and_application_have_no_framework_imports() -> None:
    source_root = Path(__file__).parents[2] / "src" / "business_assistant"
    checked = [
        *source_root.joinpath("domain").rglob("*.py"),
        *source_root.joinpath("application").rglob("*.py"),
    ]
    violations = {
        str(path.relative_to(source_root)): imported_roots(path) & FORBIDDEN_FRAMEWORKS
        for path in checked
        if imported_roots(path) & FORBIDDEN_FRAMEWORKS
    }
    assert not violations


def test_domain_does_not_import_outer_layers() -> None:
    domain_root = Path(__file__).parents[2] / "src" / "business_assistant" / "domain"
    forbidden_fragments = ("business_assistant.application", "infrastructure", "presentation")
    violations: list[str] = []
    for path in domain_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ]
        imported_modules.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        if any(
            fragment in module for module in imported_modules for fragment in forbidden_fragments
        ):
            violations.append(str(path.relative_to(domain_root)))
    assert not violations


def test_telegram_presentation_does_not_import_persistence_or_orm() -> None:
    telegram_root = (
        Path(__file__).parents[2] / "src" / "business_assistant" / "presentation" / "telegram"
    )
    forbidden_fragments = (
        "business_assistant.infrastructure.persistence",
        "sqlalchemy",
        "asyncpg",
    )
    violations: list[str] = []
    for path in telegram_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ]
        modules.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        if any(fragment in module for module in modules for fragment in forbidden_fragments):
            violations.append(str(path.relative_to(telegram_root)))
    assert not violations
