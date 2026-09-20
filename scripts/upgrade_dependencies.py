"""
Upgrades the pinned direct dependencies to their latest versions, then refreshes the transitive ones.

Run it with `make upgrade-deps` (or `make upgrade-deps-dry-run` to only list what would change).
Outside the package, so it isn't linted, covered or shipped. It needs only the standard library and uv.

The direct dependencies are pinned with `==` in pyproject.toml, so `uv lock --upgrade` alone never
moves them; each one is re-pinned with `uv add`. `uv tree --outdated --depth 1` lines look like:

    ├── pylint v4.0.5 (group: dev) (latest: v4.0.8)
    ├── google-api-python-client v2.200.0

Only lines with a `(latest: ...)` are out of date; `(group: dev)` marks a development tool.
"""

import argparse
import re
import subprocess
import sys
from typing import NamedTuple

TREE_LINE = re.compile(r"^[├└]── (?P<name>\S+) v(?P<current>\S+)(?P<rest>.*)$")
GROUP = re.compile(r"\(group: (?P<group>[^)]+)\)")
LATEST = re.compile(r"\(latest: v(?P<latest>[^)]+)\)")


class Outdated(NamedTuple):
    """A direct dependency with a newer version available."""
    name: str
    current: str
    latest: str
    group: str | None  # None for a runtime dependency


def run(command: list[str], capture: bool = False) -> str:
    """Runs a command, echoing it first; exits the script if it fails."""
    print(f"$ {' '.join(command)}", flush=True)
    result = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE if capture else None)
    if result.returncode != 0:
        sys.exit(f"'{' '.join(command)}' failed with exit code {result.returncode}.")
    return result.stdout if capture else ""


def parse_outdated(tree_output: str) -> list[Outdated]:
    """Picks the out-of-date direct dependencies out of `uv tree --outdated --depth 1`."""
    outdated = []
    for line in tree_output.splitlines():
        match = TREE_LINE.match(line)
        if not match:
            continue
        latest = LATEST.search(match["rest"])
        if not latest:
            continue
        group = GROUP.search(match["rest"])
        outdated.append(Outdated(match["name"], match["current"], latest["latest"], group["group"] if group else None))
    return outdated


def add_command(dep: Outdated) -> list[str]:
    """The `uv add` that re-pins one dependency (in its dependency group if it has one)."""
    command = ["uv", "add"]
    if dep.group:
        command += ["--group", dep.group]
    return command + [f"{dep.name}=={dep.latest}"]


def main() -> None:
    """Re-pins every outdated direct dependency, then runs `uv lock --upgrade`."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--dry-run", action="store_true", help="list the upgrades without changing anything")
    args = parser.parse_args()

    tree = run(["uv", "tree", "--outdated", "--depth", "1"], capture=True)
    print(tree)
    outdated = parse_outdated(tree)

    to_upgrade = outdated

    if not to_upgrade:
        print("Every direct dependency is up to date.")
    for dep in to_upgrade:
        label = f" ({dep.group})" if dep.group else ""
        print(f"{'Would upgrade' if args.dry_run else 'Upgrading'} {dep.name}{label}: {dep.current} -> {dep.latest}")

    if args.dry_run:
        print("Dry run: nothing changed. It would then run `uv lock --upgrade` for the transitive dependencies.")
        return

    for dep in to_upgrade:
        run(add_command(dep))
    run(["uv", "lock", "--upgrade"])
    print("\nDone. Review `git diff pyproject.toml uv.lock`, then run pylint and pytest "
          "(docs/playbook.md, 1.2) before committing.")


if __name__ == "__main__":
    main()
