#!/usr/bin/env python3
"""
kb_coverage.py — Living Atlas KB test-inventory scanner

The semantic index cannot answer "how well tested is component X?": the
blocklist in repos.yml drops `test/`, `tests/` and `integration-test/`, so not a
single test file is embedded, and the API exposes no per-repo filter anyway.

What it *can* use is the other half of the KB: the persistent clones that
kb_indexer keeps under {KB_HOME}/repos and the watcher refreshes hourly. This
script walks those working trees and writes data/testing.json mapping
"org/name" -> test counts by type, plus the coverage tooling configured in the
build. No embedding, no network — just a filesystem walk.

It is NOT line coverage: measuring that needs a full build per repo (JDK,
Grails, Maven/Gradle toolchains). What you get is the test inventory plus
whether coverage is measured in CI at all, which is the question people
actually ask when they ask "how covered is this?".

Usage:
  python3 scripts/kb_coverage.py --all            # scan every cloned repo
  python3 scripts/kb_coverage.py --repo ORG/NAME  # rescan one repo's entry
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

# Deployed side-by-side in {kb_home}/scripts, so a flat import works.
from kb_indexer import KB_HOME, REPOS_DIR, expand_repos, load_manifest

# ── Config ────────────────────────────────────────────────────────────────────

TESTING_FILE = Path(
    os.environ.get("KB_TESTING_FILE", KB_HOME / "data" / "testing.json")
)

# Not the indexer's blocklist: that one is tuned to keep noise out of the
# embeddings. Here we only need to stay out of build output and dependencies.
SKIP_DIRS = {
    ".git", "node_modules", "build", "target", "out", "dist", "vendor",
    ".gradle", ".idea", "bower_components", "__pycache__", ".venv", "venv",
}

CODE_EXT = {
    ".java", ".groovy", ".kt", ".scala", ".py", ".js", ".ts", ".dart",
    ".jsx", ".tsx", ".gsp", ".feature", ".rb", ".go",
}

BUILD_FILES = {
    "pom.xml", "build.gradle", "build.gradle.kts", "build.sbt", "package.json",
    "pubspec.yaml", "requirements.txt", "setup.py", "pyproject.toml", "tox.ini",
    "setup.cfg", "gradle.properties", "codecov.yml", ".codecov.yml",
    "sonar-project.properties",
}
CI_FILES = {"jenkinsfile", ".travis.yml", ".gitlab-ci.yml"}

GIT_TIMEOUT = 20

# ── Counting test cases ───────────────────────────────────────────────────────
# Counting @Test alone would report ~zero tests for every Grails app in the ALA
# stack, which is Spock: feature methods are quoted strings with no annotation.
# One regex per test framework, picked by file extension.

RE_JUNIT_ANN = re.compile(
    r"^\s*@(Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b", re.M
)
RE_JUNIT3 = re.compile(r"^\s*public\s+void\s+test\w*\s*\(", re.M)
RE_SPOCK = re.compile(r'^\s*(?:def|void)\s+(?:"[^"]+"|\'[^\']+\')\s*\(', re.M)
RE_PY = re.compile(r"^\s*(?:async\s+)?def\s+test\w*\s*\(", re.M)
RE_JS = re.compile(r"^\s*(?:it|test|testWidgets)\s*(?:\.\w+)?\s*\(", re.M)
RE_FEATURE = re.compile(r"^\s*Scenario(?:\s+Outline)?\s*:", re.M)

# ── Classifying a test file ───────────────────────────────────────────────────

E2E_DIRS = {
    "cypress", "e2e", "integration_test", "playwright", "functional-test",
    "functional-tests", "acceptance-test", "acceptance-tests", "uitest", "uitests",
}
INT_DIRS = {"integration-test", "integration-tests"}
UNIT_DIRS = {"test", "tests", "spec", "specs"}

RE_E2E_FILE = re.compile(r"(?:^|[/.-])(e2e|cypress|playwright|selenium|geb)\b", re.I)
RE_INT_FILE = re.compile(r"(IT|ITCase|IntegrationTest|IntegrationSpec|IntSpec)\.\w+$")
RE_TEST_FILE = re.compile(
    r"(Test|Tests|TestCase|Spec)\.(java|groovy|kt|scala)$"
    r"|^test_.*\.py$|_test\.py$|_test\.dart$|_test\.go$"
    r"|\.(test|spec)\.(js|jsx|ts|tsx)$"
)

RE_CONTEXT = re.compile(
    r"@SpringBootTest|Testcontainers|GenericContainer|@MicronautTest|@Integration\b"
)
# Browser-driving tests are e2e wherever they live. This matters: Grails puts
# Geb specs under src/integration-test, so classifying by path alone would file
# every ALA browser test as an integration test.
RE_BROWSER = re.compile(
    r"\bgeb\.(spock|Browser)|GebSpec|GebReportingSpec|browser\.(go|at)\b"
    r"|@playwright/test|\bpage\.goto\(|from ['\"]cypress|\bcy\.\w+\(|webdriver|selenium",
    re.I,
)

# ── Coverage tooling signals ──────────────────────────────────────────────────

COV_SIGNALS = {
    "jacoco": re.compile(r"jacoco", re.I),
    "cobertura": re.compile(r"cobertura", re.I),
    "sonar": re.compile(r"sonar", re.I),
    "codecov": re.compile(r"codecov", re.I),
    "coveralls": re.compile(r"coveralls", re.I),
    "pytest-cov": re.compile(r"pytest-cov|--cov\b", re.I),
    "lcov": re.compile(r"\blcov\b", re.I),
}
RE_BADGE_PCT = re.compile(r"coverage[^)\n]{0,80}?(\d{1,3})%", re.I)
# Explicit test invocations only. `gradle build` and `mvn package` also run
# tests, so a False here means "no explicit call found", not "untested".
RE_CI_TEST = re.compile(
    r"mvn[^\n]*\btest\b|gradle[^\n]*\btest\b|pytest|npm[^\n]*\btest\b|flutter test",
    re.I,
)

# ── Plain-language rating ─────────────────────────────────────────────────────
# Raw case counts mean nothing without the size of the thing being tested, and
# "cases per kLOC" means nothing to anyone who does not read code. These bands
# turn the ratio into something a report can put in front of a manager. They are
# calibrated on the 50-odd repos in the manifest: the GBIF repos all land in
# 'moderate' or 'good', the untested Grails hubs in 'minimal' or 'none'.
LEVEL_BANDS = [
    (10.0, "good"),
    (5.0, "moderate"),
    (2.0, "low"),
    (0.01, "minimal"),
]

# Below this much production code the ratio is noise: apikey, a 1 kLOC wrapper
# with 7 tests, scored higher than biocache-service. Say "too small to rate"
# instead of emitting a verdict nobody should act on. There is deliberately no
# floor on the number of *cases* — spatial-service has 14 over 84 kLOC, and
# that is the most important finding in the set, not a rounding error.
MIN_LOC_TO_RATE = 2000

LEVEL_TEXT = {
    "good": "well covered by automated tests",
    "moderate": "reasonably tested",
    "low": "thinly tested",
    "minimal": "barely tested",
    "none": "no automated tests at all",
    "unscored": "too small to rate meaningfully",
}


def rate(cases_per_kloc: float, total_cases: int, main_loc: int = 0) -> str:
    if main_loc < MIN_LOC_TO_RATE:
        return "unscored"
    if total_cases == 0:
        return "none"
    for threshold, label in LEVEL_BANDS:
        if cases_per_kloc >= threshold:
            return label
    return "minimal"


def assess(entry: dict) -> str:
    """One sentence a non-developer can act on."""
    parts = [LEVEL_TEXT[entry["test_level"]]]
    if entry["has_e2e"]:
        parts.append("has end-to-end tests that drive a real browser")
    else:
        parts.append("no end-to-end tests")
    parts.append(
        "coverage is measured in the build (%s)" % ", ".join(entry["coverage_tools"])
        if entry["coverage_measured"]
        else "coverage is never measured"
    )
    return "; ".join(parts) + "."


log = logging.getLogger("kb_coverage")


# ── Scanning ──────────────────────────────────────────────────────────────────

def classify(rel: str, name: str, text: str) -> str:
    """Return 'main', 'unit', 'integration' or 'e2e' for one source file."""
    parts = rel.split("/")
    comps = set(parts[:-1])

    # Anything under src/main is production, whatever it is called. atlas-index
    # really does ship a src/main/java/au/org/ala/Test.java, which the filename
    # rules below would otherwise count as a test file.
    if "src/main/" in rel:
        return "main"

    if name.endswith(".feature"):
        return "e2e"
    if comps & E2E_DIRS or RE_E2E_FILE.search(rel.lower()):
        return "e2e"
    if comps & INT_DIRS or RE_INT_FILE.search(name):
        return "e2e" if RE_BROWSER.search(text) else "integration"

    if not (comps & UNIT_DIRS or RE_TEST_FILE.search(name)):
        return "main"
    if RE_BROWSER.search(text):
        return "e2e"
    if RE_CONTEXT.search(text):
        return "integration"
    return "unit"


def count_cases(name: str, text: str) -> int:
    """Number of declared test cases in one test file, by framework."""
    if name.endswith(".feature"):
        return len(RE_FEATURE.findall(text))
    if name.endswith((".java", ".kt", ".scala")):
        ann = len(RE_JUNIT_ANN.findall(text))
        # JUnit 3 naming only when the file has no JUnit 4/5 annotation at all,
        # otherwise "@Test public void testFoo()" would be counted twice.
        return ann if ann else len(RE_JUNIT3.findall(text))
    if name.endswith(".groovy"):
        return len(RE_JUNIT_ANN.findall(text)) + len(RE_SPOCK.findall(text))
    if name.endswith(".py"):
        return len(RE_PY.findall(text))
    if name.endswith((".js", ".jsx", ".ts", ".tsx", ".dart")):
        return len(RE_JS.findall(text))
    return 0


def detect_stack(build_blob: str, langs: dict) -> list[str]:
    stack = []
    if "<artifactId>" in build_blob:
        stack.append("maven")
    if re.search(r"org\.grails", build_blob):
        stack.append("grails")
    elif re.search(r"apply plugin|plugins\s*\{", build_blob):
        stack.append("gradle")
    if ".dart" in langs:
        stack.append("dart")
    if re.search(r'"scripts"\s*:', build_blob):
        stack.append("npm")
    if re.search(r"pytest|setuptools|\[project\]", build_blob):
        stack.append("python")
    return stack


def scan_repo(repo_dir: Path) -> dict:
    """Walk one checkout and return its test inventory."""
    res = {
        "main_files": 0,
        "main_loc": 0,
        "unit": {"files": 0, "cases": 0},
        "integration": {"files": 0, "cases": 0},
        "e2e": {"files": 0, "cases": 0},
        "languages": {},
    }
    build_text: list[str] = []
    ci_text: list[str] = []
    readme_text: list[str] = []

    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            rel = str(fp.relative_to(repo_dir))
            low = fn.lower()

            if low in BUILD_FILES:
                build_text.append(read_text(fp))
            if rel.startswith(".github/workflows/") or low in CI_FILES:
                ci_text.append(read_text(fp))
            if low.startswith("readme"):
                readme_text.append(read_text(fp))

            if fp.suffix.lower() not in CODE_EXT:
                continue
            text = read_text(fp)
            kind = classify(rel, fn, text)
            if kind == "main":
                res["main_files"] += 1
                res["main_loc"] += text.count("\n") + 1
                ext = fp.suffix.lower()
                res["languages"][ext] = res["languages"].get(ext, 0) + 1
            else:
                res[kind]["files"] += 1
                res[kind]["cases"] += count_cases(fn, text)

    build_blob = "\n".join(build_text)
    ci_blob = "\n".join(ci_text)
    res["coverage_tools"] = sorted(
        k for k, rx in COV_SIGNALS.items() if rx.search(build_blob + "\n" + ci_blob)
    )
    res["has_ci"] = bool(ci_blob)
    res["ci_runs_tests"] = bool(ci_blob and RE_CI_TEST.search(ci_blob))
    res["stack"] = detect_stack(build_blob, res["languages"])
    res["badge_coverage_pct"] = None
    for rt in readme_text:
        m = RE_BADGE_PCT.search(rt)
        if m:
            res["badge_coverage_pct"] = int(m.group(1))
            break

    res["total_cases"] = sum(res[k]["cases"] for k in ("unit", "integration", "e2e"))
    res["test_files"] = sum(res[k]["files"] for k in ("unit", "integration", "e2e"))
    res["cases_per_kloc"] = (
        round(res["total_cases"] / (res["main_loc"] / 1000), 2) if res["main_loc"] else 0.0
    )

    # Derived, plain-language fields: the point of the whole artifact is that
    # someone who does not read Java can tell which components are exposed.
    res["has_e2e"] = res["e2e"]["cases"] > 0
    res["coverage_measured"] = bool(res["coverage_tools"])
    res["test_level"] = rate(res["cases_per_kloc"], res["total_cases"], res["main_loc"])
    res["assessment"] = assess(res)
    return res


def read_text(path: Path) -> str:
    """Read a file as text, tolerating binary noise and unreadable files."""
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def last_commit(repo_dir: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "log", "-1", "--format=%cs"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


# ── testing.json ──────────────────────────────────────────────────────────────

def load_testing() -> dict:
    if not TESTING_FILE.exists():
        return {}
    try:
        return json.loads(TESTING_FILE.read_text())
    except Exception:
        log.warning("%s unreadable — starting fresh", TESTING_FILE)
        return {}


def write_testing(data: dict) -> None:
    """Write atomically: the API reads this file while the watcher rewrites it."""
    TESTING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TESTING_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, TESTING_FILE)


def scannable_repos(manifest: dict) -> list[dict]:
    """Git repos worth scanning: no wikis (docs, no code), no local sources."""
    return [
        r for r in expand_repos(manifest)
        if not r.get("is_wiki") and not r.get("is_local")
    ]


def run(repos: list[dict]) -> None:
    data = load_testing()
    for repo_meta in repos:
        org, name = repo_meta["org"], repo_meta["name"]
        key = f"{org}/{name}"
        repo_dir = REPOS_DIR / org / name
        if not repo_dir.is_dir():
            log.warning("%s: not cloned — skipping", key)
            data[key] = {"status": "not_cloned"}
            continue
        try:
            entry = scan_repo(repo_dir)
        except Exception as e:
            log.error("%s: scan failed — %s", key, e)
            continue
        entry["status"] = "ok"
        entry["last_commit"] = last_commit(repo_dir)
        data[key] = entry
        log.info(
            "%s: %d cases (%d unit / %d integration / %d e2e) over %d kLOC",
            key, entry["total_cases"], entry["unit"]["cases"],
            entry["integration"]["cases"], entry["e2e"]["cases"],
            entry["main_loc"] // 1000,
        )
    write_testing(data)
    log.info("Wrote %s (%d repos)", TESTING_FILE, len(data))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Living Atlas KB test-inventory scanner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Scan every cloned repo")
    group.add_argument("--repo", metavar="ORG/NAME", help="Rescan a single repo")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    repos = scannable_repos(load_manifest())
    if args.repo:
        repos = [r for r in repos if f"{r['org']}/{r['name']}" == args.repo]
        if not repos:
            log.error("Repo not in manifest: %s", args.repo)
            sys.exit(1)

    run(repos)


if __name__ == "__main__":
    main()
