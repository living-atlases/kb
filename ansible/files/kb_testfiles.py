#!/usr/bin/env python3
"""
kb_testfiles.py — is this file a test, and what kind?

Shared by the indexer (which tags test chunks `content_type="test"` so they can
be searched or filtered out on their own) and the coverage scanner (which counts
them). Kept in its own module because importing it the other way round would be
circular: kb_coverage already imports the manifest helpers from kb_indexer.

Classification is by content where the path lies. Grails keeps its Geb browser
specs under src/integration-test, so a path-only rule would file every ALA
browser test as an integration test.
"""

import re

# Test files worth embedding: real test code. Test *resources* — the JSON,
# XML and CSV fixtures that live in the same tree — are 78% of the volume
# (126k chunks against 28k of code, checklistbank alone 59k) and answer no
# question anyone asks in prose.
TEST_CODE_EXTENSIONS = {
    ".java", ".groovy", ".kt", ".scala", ".py",
    ".js", ".jsx", ".ts", ".tsx", ".dart", ".feature", ".sql",
}

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
