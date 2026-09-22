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
    assert entry["has_e2e"] is True
    assert entry["coverage_measured"] is True
    assert "end-to-end" in entry["assessment"]
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
