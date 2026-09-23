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


# ── Vendored third-party assets ───────────────────────────────────────────────
# Grails apps commit their front-end libraries into the repo: volunteer-portal
# carries 455k lines of TinyMCE and friends, biocollect 284k. Counting those as
# production code made volunteer-portal look like the worst-tested component in
# the manifest (0.34 cases/kLOC) when the figure over its own code is 4.4 — a
# manager acting on that table would have funded tests for TinyMCE.
# The indexer blocklist already treats these directories as vendored; this
# applies the same judgement to the LOC count.

VENDOR_DIRS = {
    "assets", "javascripts", "js", "vendor", "thirdparty", "third-party",
    "lib", "libs", "static", "bower_components", "webjars",
}

VENDOR_NAMES = re.compile(
    r"(jquery|bootstrap|angular|tinymce|datatables|moment|lodash|underscore"
    r"|d3|leaflet|select2|openlayers|highcharts|modernizr|require|backbone"
    r"|knockout|ckeditor|fontawesome)", re.I,
)

WEB_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}


def is_vendored(rel: str, name: str, ext: str) -> bool:
    """True for a third-party library checked into the repo.

    Only web assets qualify: a Java file under a directory called `lib` is
    still somebody's code, but `grails-app/assets/javascripts/jquery-ui.js`
    is 18k lines nobody here wrote or can patch.
    """
    if ext not in WEB_EXTENSIONS:
        return False
    comps = set(rel.split("/")[:-1])
    return bool(comps & VENDOR_DIRS) or bool(VENDOR_NAMES.search(name)) or ".min." in name
