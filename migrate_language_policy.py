"""Migrate an existing generated site to the Factory's current locale policy."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from project_contract import FIXED_LANGUAGES


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def migrate(project: Path) -> list[str]:
    project = project.expanduser().resolve()
    if not (project / "package.json").is_file() or not (project / "intake").is_dir():
        raise RuntimeError(f"not a generated Game Wiki project: {project}")

    identity_path = project / "intake" / "site-identity.json"
    plan_path = project / "intake" / "site-plan.json"
    identity = _read(identity_path)
    plan = _read(plan_path)
    previous = list(plan.get("languages") or identity.get("LANGUAGES") or [])
    removed = [locale for locale in previous if locale not in FIXED_LANGUAGES]

    identity["LANGUAGES"] = list(FIXED_LANGUAGES)
    plan["languages"] = list(FIXED_LANGUAGES)
    for category in plan.get("categories") or []:
        for field in ("labels", "descriptions"):
            values = category.get(field)
            if isinstance(values, dict):
                category[field] = {
                    locale: values[locale] for locale in FIXED_LANGUAGES if locale in values
                }
    _write(identity_path, identity)
    _write(plan_path, plan)

    for locale in removed:
        for target in (
            project / "intake" / f"site-content.{locale}.json",
            project / "intake" / "articles" / locale,
            project / "content" / locale,
            project / "src" / "locales" / f"{locale}.json",
        ):
            resolved = target.resolve()
            if project not in resolved.parents:
                raise RuntimeError(f"refusing to remove path outside project: {resolved}")
            if resolved.is_dir():
                shutil.rmtree(resolved)
            elif resolved.is_file():
                resolved.unlink()
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    removed = migrate(args.project)
    print(json.dumps({"languages": FIXED_LANGUAGES, "removed": removed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
