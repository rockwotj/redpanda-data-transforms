#!/usr/bin/env python3

import sys
try:
    import yaml
except ImportError:
    print("Please install pyyaml via `pip install pyyaml`")
    sys.exit(1)

import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass

ROOT_DIR = Path(__file__).parent

@dataclass(order=True, frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @staticmethod
    def parse(s: str):
        s = s.removeprefix("v")
        p = s.split(".")
        if len(p) != 3:
            raise ValueError(f"invalid version: {s}")
        (major, minor, patch) = p
        return Version(int(major), int(minor), int(patch))
    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"
    def next_major(self):
        return Version(self.major + 1, 0, 0)
    def next_minor(self):
        return Version(self.major, self.minor + 1, 0)
    def next_patch(self):
        return Version(self.major, self.minor, self.patch + 1)

ZERO_VERISON = Version(0, 0, 0)

def list_versions(project: str):
    subprocess.check_call(
        ["git", "fetch", "--tags", "--all"],
        cwd=ROOT_DIR,
    )
    output = subprocess.check_output(
        ["git", "tag"],
        cwd=ROOT_DIR,
        text=True
    )
    prefix = f"{project}-"
    return [Version.parse(tag.removeprefix(prefix)) for tag in output.splitlines() if tag.startswith(prefix)]

@dataclass(frozen=True)
class BuildArtifacts:
    project: str
    wasm_file: Path
    transform_yaml: Path

def build(project: str) -> BuildArtifacts:
    subprocess.check_call(
        ["rpk", "transform", "build"],
        cwd=ROOT_DIR / project,
    )
    return BuildArtifacts(
        project=project,
        wasm_file=ROOT_DIR / project / f"{project}.wasm",
        transform_yaml=ROOT_DIR / project / "transform.yaml",
    )

def make_release(version: Version, artifacts: BuildArtifacts):
    transform_file = None
    with open(artifacts.transform_yaml) as f:
        transform_file = yaml.safe_load(f)
    required_env = []
    for k, v in transform_file.get("env", {}).items():
        if v == "<required>":
            required_env.append(k)

    sep = " \\\n" + (" " * 4)
    env_vars = ""
    for v in required_env:
        env_vars += sep
        env_vars += f"--env-var='{v}=[VALUE]'"
    notes = f"""
{transform_file["description"]}

```
# Deploy this transform using:
rpk transform deploy @redpanda-data/regex@{version} \\
    --name [NAME] \\
    --input-topic [TOPIC] \\
    --output-topic [TOPIC]{env_vars}
```
    """
    subprocess.check_call(
        ["gh", "release", "create", 
         f"{artifacts.project}-{version}", artifacts.transform_yaml, artifacts.wasm_file,
         "--notes", notes,
         "--title", f"{artifacts.project.title()} {version}"
         ],
        cwd=ROOT_DIR,
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    projects = [
        child.name for child 
        in ROOT_DIR.iterdir()
        if (child / "transform.yaml").exists()
    ]

    parser.add_argument('--project', choices=projects, required=True)
    parser.add_argument('--version', choices=['major', 'minor', 'patch'], required=True)
    args = parser.parse_args()
    latest = max(list_versions(args.project), default=ZERO_VERISON)
    if args.version == 'major':
        latest = latest.next_major()
    elif args.version == 'minor':
        latest = latest.next_minor()
    elif args.version == 'patch':
        latest = latest.next_patch()
    artifacts = build(args.project) 
    make_release(latest, artifacts)
    

