"""Tests for kb_coverage.py — test-inventory scanner (no network, no ChromaDB)."""

import json

import pytest

import kb_coverage as kc


# ── count_cases: one framework per stack ──────────────────────────────────────

def test_counts_junit_annotations():
    src = """
    @Test
    void findsRecord() {}

    @ParameterizedTest
    @ValueSource(ints = {1, 2})
    void handles(int n) {}

    @RepeatedTest(3)
    void retries() {}
    """
    assert kc.count_cases("FooTest.java", src) == 3


def test_junit3_not_double_counted_with_annotations():
    """`@Test public void testFoo()` is one case, not two."""
    src = """
    @Test
    public void testFindsRecord() {}

    @Test
    public void testHandlesNull() {}
    """
    assert kc.count_cases("FooTest.java", src) == 2


def test_counts_junit3_when_no_annotations_present():
    src = """
    public void testFindsRecord() {}
    public void testHandlesNull() {}
    """
    assert kc.count_cases("FooTest.java", src) == 2


def test_counts_spock_feature_methods():
    """Half the ALA stack is Grails/Spock: feature methods carry no @Test."""
    src = '''
    class CollectionSpec extends Specification {
        def "returns the collection for a known uid"() {
            expect: true
        }

        void "rejects an unknown uid"() {
            expect: true
        }
    }
    '''
    assert kc.count_cases("CollectionSpec.groovy", src) == 2


def test_counts_spock_and_junit_in_same_groovy_file():
    src = '''
    @Test
    void oldStyle() {}

    def "new style"() {}
    '''
    assert kc.count_cases("MixedSpec.groovy", src) == 2


def test_counts_pytest_functions():
    src = """
def test_one():
    pass

async def test_two():
    pass

def helper():
    pass
"""
    assert kc.count_cases("test_thing.py", src) == 2


def test_counts_js_and_playwright_cases():
    src = """
test('loads the home page', async ({ page }) => {});
it('renders a banner', () => {});
describe('suite', () => {});
"""
    assert kc.count_cases("home.spec.ts", src) == 2


def test_counts_cucumber_scenarios():
    src = """
Feature: search
  Scenario: a plain search
  Scenario Outline: a parameterised search
"""
    assert kc.count_cases("search.feature", src) == 2


def test_unknown_extension_counts_nothing():
    assert kc.count_cases("index.gsp", "<g:each>@Test</g:each>") == 0


# ── classify: unit / integration / e2e / main ─────────────────────────────────

@pytest.mark.parametrize("rel,expected", [
    ("src/main/java/au/org/ala/Service.java", "main"),
    ("grails-app/services/au/org/ala/Thing.groovy", "main"),
    ("src/test/java/au/org/ala/ServiceTest.java", "unit"),
    ("src/test/groovy/au/org/ala/ThingSpec.groovy", "unit"),
    ("tests/test_indexer.py", "unit"),
    ("src/integration-test/groovy/au/org/ala/ThingIntegrationSpec.groovy", "integration"),
    ("src/test/java/au/org/ala/ServiceITCase.java", "integration"),
    ("cypress/e2e/search.cy.js", "e2e"),
    ("admin-ui/tests/synthetic/Home.spec.ts", "unit"),
    ("features/search.feature", "e2e"),
    ("integration_test/app_test.dart", "e2e"),
])
def test_classify_by_path(rel, expected):
    assert kc.classify(rel, rel.split("/")[-1], "") == expected


def test_springboot_test_is_integration_not_unit():
    src = "@SpringBootTest\nclass RegistryIT { @Test void boots() {} }"
    assert kc.classify("src/test/java/RegistryTest.java", "RegistryTest.java", src) == "integration"


def test_geb_spec_under_integration_test_is_e2e():
    """Grails puts browser specs in src/integration-test — path alone would lie."""
    src = "import geb.spock.GebReportingSpec\nclass SearchSpec extends GebReportingSpec {}"
    rel = "src/integration-test/groovy/pages/SearchSpec.groovy"
    assert kc.classify(rel, "SearchSpec.groovy", src) == "e2e"


def test_playwright_spec_under_tests_is_e2e():
    src = "import { test } from '@playwright/test';\ntest('x', async ({page}) => { await page.goto('/'); });"
    assert kc.classify("admin-ui/tests/Home.spec.ts", "Home.spec.ts", src) == "e2e"


def test_production_file_named_like_a_test_is_not_a_test():
    assert kc.classify("src/main/java/au/org/ala/Test.java", "Test.java", "") == "main"


# ── scan_repo over a synthetic checkout ───────────────────────────────────────

def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def fake_repo(tmp_path):
    root = tmp_path / "org" / "thing"
    _write(root, "pom.xml", "<project><artifactId>thing</artifactId>"
                            "<plugin><artifactId>jacoco-maven-plugin</artifactId></plugin></project>")
    _write(root, "README.md", "# thing")
    _write(root, "src/main/java/Service.java", "class Service {}\n" * 10)
    _write(root, "src/test/java/ServiceTest.java", "@Test\nvoid a() {}\n@Test\nvoid b() {}")
    _write(root, "src/integration-test/groovy/ThingIntegrationSpec.groovy",
           'def "boots"() {}')
    _write(root, "cypress/e2e/search.cy.js", "it('searches', () => { cy.visit('/'); });")
    _write(root, ".github/workflows/ci.yml", "jobs:\n  t:\n    steps:\n      - run: mvn test")
    _write(root, "node_modules/dep/index.js", "it('should not be counted', () => {});")
    _write(root, "build/generated/Gen.java", "@Test void generated() {}")
    return root


def test_scan_repo_counts_by_type(fake_repo):
    res = kc.scan_repo(fake_repo)
    assert res["unit"] == {"files": 1, "cases": 2}
    assert res["integration"] == {"files": 1, "cases": 1}
    assert res["e2e"] == {"files": 1, "cases": 1}
    assert res["total_cases"] == 4
    assert res["test_files"] == 3


def test_scan_repo_ignores_dependencies_and_build_output(fake_repo):
    res = kc.scan_repo(fake_repo)
    # node_modules/ and build/ would otherwise add two phantom cases.
    assert res["total_cases"] == 4
    assert res["main_files"] == 1


def test_scan_repo_detects_stack_and_coverage_tooling(fake_repo):
    res = kc.scan_repo(fake_repo)
    assert "maven" in res["stack"]
    assert res["coverage_tools"] == ["jacoco"]
    assert res["ci_runs_tests"] is True
    assert res["has_ci"] is True


def test_scan_repo_reports_density(fake_repo):
    res = kc.scan_repo(fake_repo)
    assert res["main_loc"] > 0
    assert res["cases_per_kloc"] == round(4 / (res["main_loc"] / 1000), 2)


def test_scan_repo_with_no_production_code_has_zero_density(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    res = kc.scan_repo(root)
    assert res["cases_per_kloc"] == 0.0
    assert res["total_cases"] == 0


def test_badge_percentage_parsed_from_readme(tmp_path):
    root = tmp_path / "badged"
    _write(root, "README.md", "![coverage](https://img.shields.io/badge/coverage-87%25-green)")
    assert kc.scan_repo(root)["badge_coverage_pct"] == 87


# ── testing.json ──────────────────────────────────────────────────────────────

def test_write_and_load_testing_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "data" / "testing.json"
    monkeypatch.setattr(kc, "TESTING_FILE", target)
    payload = {"gbif/pipelines": {"total_cases": 1126, "status": "ok"}}
    kc.write_testing(payload)
    assert json.loads(target.read_text()) == payload
    assert kc.load_testing() == payload


def test_write_testing_is_atomic(tmp_path, monkeypatch):
    """The API reads this file while the watcher rewrites it — no partial reads."""
    target = tmp_path / "testing.json"
    monkeypatch.setattr(kc, "TESTING_FILE", target)
    kc.write_testing({"a": 1})
    assert not list(tmp_path.glob("*.tmp"))


def test_load_testing_tolerates_corrupt_file(tmp_path, monkeypatch):
    target = tmp_path / "testing.json"
    target.write_text("{not json")
    monkeypatch.setattr(kc, "TESTING_FILE", target)
    assert kc.load_testing() == {}


def test_load_testing_missing_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "TESTING_FILE", tmp_path / "nope.json")
    assert kc.load_testing() == {}


# ── run(): merge semantics and missing clones ─────────────────────────────────

def test_run_marks_uncloned_repos_without_dropping_others(tmp_path, monkeypatch):
    monkeypatch.setattr(kc, "TESTING_FILE", tmp_path / "testing.json")
    monkeypatch.setattr(kc, "REPOS_DIR", tmp_path / "repos")
    kc.write_testing({"gbif/pipelines": {"total_cases": 1126, "status": "ok"}})

    kc.run([{"org": "AtlasOfLivingAustralia", "name": "ala-bie"}])

    data = kc.load_testing()
    assert data["AtlasOfLivingAustralia/ala-bie"] == {"status": "not_cloned"}
    # A single-repo run rewrites the whole file, so the other entry must survive.
    assert data["gbif/pipelines"]["total_cases"] == 1126


def test_run_scans_a_cloned_repo(tmp_path, monkeypatch, fake_repo):
    monkeypatch.setattr(kc, "TESTING_FILE", tmp_path / "testing.json")
    monkeypatch.setattr(kc, "REPOS_DIR", fake_repo.parent.parent)

    kc.run([{"org": "org", "name": "thing"}])

    entry = kc.load_testing()["org/thing"]
    assert entry["status"] == "ok"
    assert entry["total_cases"] == 4


def test_scannable_repos_skips_wikis_and_local_sources(monkeypatch):
    monkeypatch.setattr(kc, "expand_repos", lambda m: [
        {"org": "gbif", "name": "ipt"},
        {"org": "gbif", "name": "ipt.wiki", "is_wiki": True},
        {"org": "local", "name": "la-kb-faq", "is_local": True},
    ])
    names = [r["name"] for r in kc.scannable_repos({})]
    assert names == ["ipt"]


# ── Plain-language rating ─────────────────────────────────────────────────────

@pytest.mark.parametrize("ratio,total,loc,expected", [
    (0.0, 0, 7355, "none"),
    (0.2, 14, 84868, "minimal"),
    (1.7, 33, 19186, "minimal"),
    (2.0, 116, 58427, "low"),
    (4.9, 221, 102485, "low"),
    (5.0, 303, 46292, "moderate"),
    (9.9, 731, 89062, "moderate"),
    (11.6, 1126, 97035, "good"),
    (28.9, 2093, 72392, "good"),
])
def test_rate_bands(ratio, total, loc, expected):
    assert kc.rate(ratio, total, loc) == expected


def test_zero_cases_is_never_rated_above_none():
    """A repo with plenty of prod code and no tests must not slip into a band."""
    assert kc.rate(0.0, 0, 7355) == "none"


def test_tiny_wrapper_is_not_rated_at_all():
    """apikey: 7 cases over 1 kLOC scored 'moderate' and outranked
    biocache-service. A ratio over that little code is noise, not a verdict."""
    assert kc.rate(6.6, 7, 1058) == "unscored"


def test_very_few_cases_over_a_large_codebase_still_scores():
    """spatial-service: 14 cases over 84 kLOC. A case floor would have hidden
    the worst result in the whole manifest behind 'too small to rate'."""
    assert kc.rate(0.17, 14, 84868) == "minimal"


def test_a_small_but_genuinely_tested_service_still_scores():
    """ala-namematching-service: 4 kLOC but 149 cases — that is a real verdict."""
    assert kc.rate(35.3, 149, 4223) == "good"


def test_assessment_is_readable_without_reading_code(fake_repo):
    entry = kc.scan_repo(fake_repo)
    assert entry["test_level"] in ("none", "minimal", "low", "moderate", "good", "unscored")
    # One browser test in the fixture: real, but not a suite.
    assert entry["e2e_status"] == "token"
    assert entry["has_e2e"] is False
    assert entry["coverage_measured"] is True
    assert "browser test" in entry["assessment"]
    assert "jacoco" in entry["assessment"]
    assert entry["assessment"].endswith(".")


def test_assessment_names_the_gaps(tmp_path):
    root = tmp_path / "bare"
    _write(root, "src/main/java/Service.java", "class Service {}\n" * 500)
    _write(root, "src/test/java/ServiceTest.java", "@Test\nvoid a() {}")
    entry = kc.scan_repo(root)
    assert entry["has_e2e"] is False
    assert entry["coverage_measured"] is False
    assert "no end-to-end tests" in entry["assessment"]
    assert "coverage is never measured" in entry["assessment"]


# ── --report ──────────────────────────────────────────────────────────────────

REPORT_DATA = {
    "gbif/pipelines": {
        "status": "ok", "test_level": "good", "total_cases": 1126,
        "unit": {"cases": 988, "files": 218}, "integration": {"cases": 138, "files": 36},
        "e2e": {"cases": 0, "files": 0}, "e2e_status": "none", "main_loc": 97035,
        "coverage_tools": ["sonar"], "cases_per_kloc": 11.6,
    },
    "AtlasOfLivingAustralia/collectory": {
        "status": "ok", "test_level": "minimal", "total_cases": 116,
        "unit": {"cases": 116, "files": 7}, "integration": {"cases": 0, "files": 0},
        "e2e": {"cases": 0, "files": 1}, "e2e_status": "scaffold", "main_loc": 58427,
        "coverage_tools": [], "cases_per_kloc": 1.99,
    },
    "AtlasOfLivingAustralia/ala-bie": {"status": "not_cloned"},
}


def test_report_groups_by_org_and_ranks_by_level():
    out = kc.render_report(REPORT_DATA)
    assert "## gbif — 1 components" in out
    assert "## AtlasOfLivingAustralia — 1 components" in out
    # Never-cloned repos have nothing to report.
    assert "ala-bie" not in out


def test_report_distinguishes_an_empty_e2e_scaffold_from_no_e2e():
    out = kc.render_report(REPORT_DATA)
    assert "empty scaffold" in out   # collectory: a directory, no cases
    assert "| no |" in out or "| no " in out  # pipelines: nothing at all


def test_report_can_be_scoped_to_one_org():
    out = kc.render_report(REPORT_DATA, org="gbif")
    assert "pipelines" in out
    assert "collectory" not in out


def test_report_on_empty_data_says_so():
    assert kc.render_report({}) == "No test data available."


def test_report_reads_the_local_artifact_when_no_api_given(tmp_path, monkeypatch):
    target = tmp_path / "testing.json"
    monkeypatch.setattr(kc, "TESTING_FILE", target)
    kc.write_testing(REPORT_DATA)
    assert kc.load_report_data(None) == REPORT_DATA


# ── e2e is a suite, not a single test ─────────────────────────────────────────

@pytest.mark.parametrize("cases,files,expected", [
    (771, 100, "yes"),
    (28, 20, "yes"),
    (13, 4, "yes"),
    (3, 1, "yes"),
    (1, 2, "token"),
    (2, 2, "token"),
    (0, 1, "scaffold"),
    (0, 0, "none"),
])
def test_e2e_status(cases, files, expected):
    assert kc.e2e_status(cases, files) == expected


def test_single_browser_test_does_not_claim_an_e2e_suite():
    """spatial-service has exactly one, and is the worst component in the set:
    'has end-to-end tests' there reads as the opposite of the truth."""
    entry = {"test_level": "minimal", "e2e_status": kc.e2e_status(1, 2),
             "coverage_measured": False, "coverage_tools": []}
    text = kc.assess(entry)
    assert "token browser test" in text
    assert "has end-to-end tests" not in text


def test_empty_scaffold_is_named_as_such():
    entry = {"test_level": "low", "e2e_status": kc.e2e_status(0, 1),
             "coverage_measured": False, "coverage_tools": []}
    assert "never filled in" in kc.assess(entry)


# ── Superseded components ─────────────────────────────────────────────────────

def test_assessment_names_the_replacement_when_superseded():
    entry = {
        "test_level": "minimal", "e2e_status": "token",
        "coverage_measured": False, "coverage_tools": [],
        "superseded_by": "AtlasOfLivingAustralia/atlas-index",
        "superseded_note": "UI replaced by atlas-index/occurrence-ui (90%)",
    }
    text = kc.assess(entry)
    assert "Being replaced by AtlasOfLivingAustralia/atlas-index" in text
    assert "occurrence-ui" in text


def test_scan_alone_never_claims_a_replacement(fake_repo):
    """scan_repo only sees a directory; the manifest knows about successors."""
    entry = kc.scan_repo(fake_repo)
    assert entry["superseded_by"] is None
    assert "Being replaced" not in entry["assessment"]


def test_run_stamps_supersession_from_the_manifest(tmp_path, monkeypatch, fake_repo):
    monkeypatch.setattr(kc, "TESTING_FILE", tmp_path / "testing.json")
    monkeypatch.setattr(kc, "REPOS_DIR", fake_repo.parent.parent)

    kc.run([{
        "org": "org", "name": "thing",
        "superseded_by": "AtlasOfLivingAustralia/atlas-index",
        "superseded_note": "UI replaced by atlas-index/occurrence-ui (90%)",
    }])

    entry = kc.load_testing()["org/thing"]
    assert entry["superseded_by"] == "AtlasOfLivingAustralia/atlas-index"
    assert "Being replaced" in entry["assessment"]


# ── Vendored libraries are not production code ────────────────────────────────

@pytest.mark.parametrize("rel,vendored", [
    ("grails-app/assets/javascripts/jquery-ui.js", True),
    ("grails-app/assets/thirdparty/angular/angular.js", True),
    ("web-app/js/bootstrap.min.js", True),
    ("src/main/webapp/lib/tinymce/tinymce.js", True),
    ("admin-ui/src/components/Search.tsx", False),
    ("src/main/groovy/au/org/ala/Service.groovy", False),
    # A Java file under a directory called lib is still somebody's code.
    ("lib/src/main/java/au/org/ala/Helper.java", False),
])
def test_is_vendored(rel, vendored):
    from kb_testfiles import is_vendored
    import os
    name = rel.split("/")[-1]
    assert is_vendored(rel, name, os.path.splitext(name)[1]) is vendored


def test_vendored_libraries_do_not_count_against_the_test_ratio(tmp_path):
    """volunteer-portal shipped as 'the worst ratio in the catalogue' (0.34)
    because 455k lines of TinyMCE counted as its production code. Over what it
    actually wrote the figure is 4.4 — a different decision entirely."""
    root = tmp_path / "grailsapp"
    _write(root, "grails-app/services/au/org/ala/Thing.groovy", "class Thing {}\n" * 3000)
    _write(root, "grails-app/assets/javascripts/tinymce.js", "// vendored\n" * 50000)
    _write(root, "src/test/groovy/ThingSpec.groovy", 'def "works"() {}\n' * 20)

    res = kc.scan_repo(root)
    assert res["vendored_loc"] > 49000
    assert res["own_loc"] < 3100
    assert res["main_loc"] == res["own_loc"] + res["vendored_loc"]
    # Rated over its own code, not over TinyMCE.
    assert res["cases_per_kloc"] == round(20 / (res["own_loc"] / 1000), 2)
    # Over the whole tree the ratio would be 0.4 — "barely tested".
    assert round(20 / (res["main_loc"] / 1000), 2) < 1
    assert res["test_level"] == "moderate"


def test_vendored_loc_stays_visible(tmp_path):
    """The correction must not hide the problem it corrects for: 1.2M lines of
    unpatchable libraries in the repos is itself the finding."""
    root = tmp_path / "app"
    _write(root, "grails-app/assets/javascripts/jquery.js", "x\n" * 900)
    _write(root, "grails-app/services/S.groovy", "class S {}\n" * 50)
    res = kc.scan_repo(root)
    assert res["vendored_loc"] == 901   # trailing newline counts as a line
    assert res["main_loc"] == 952


def test_a_repo_that_is_all_vendored_code_is_unscored(tmp_path):
    root = tmp_path / "branding"
    _write(root, "assets/js/bootstrap.js", "x\n" * 5000)
    res = kc.scan_repo(root)
    assert res["own_loc"] == 0
    assert res["test_level"] == "unscored"


# ── CI detection names the system ─────────────────────────────────────────────

def test_jenkins_is_detected_as_ci(tmp_path):
    """GBIF runs Jenkins. Reading only .github/workflows reported its repos as
    not running tests — the opposite of the truth, and in the one direction
    that flattered the comparison."""
    root = tmp_path / "gbifish"
    _write(root, "Jenkinsfile", "pipeline { stages { stage('test') { steps { sh 'mvn test' } } } }")
    _write(root, "src/main/java/S.java", "class S {}\n" * 100)
    res = kc.scan_repo(root)
    assert res["ci_systems"] == ["jenkins"]
    assert res["has_ci"] is True


def test_several_ci_systems_are_all_reported(tmp_path):
    root = tmp_path / "both"
    _write(root, "Jenkinsfile", "pipeline {}")
    _write(root, ".travis.yml", "language: java")
    _write(root, ".github/workflows/ci.yml", "jobs: {}")
    _write(root, "src/main/java/S.java", "class S {}\n" * 100)
    assert kc.scan_repo(root)["ci_systems"] == ["github-actions", "jenkins", "travis"]


def test_no_ci_is_reported_as_none(tmp_path):
    root = tmp_path / "bare"
    _write(root, "src/main/java/S.java", "class S {}\n" * 100)
    res = kc.scan_repo(root)
    assert res["ci_systems"] == []
    assert res["has_ci"] is False
