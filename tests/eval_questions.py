"""Regression eval: real community questions vs. the KB answer layer.

The 7 questions below are real ones from the #gbif-node-developers Slack channel,
used to evaluate whether the KB can answer the community (and to catch regressions
when content/retrieval changes). `expect_sources` lists path fragments that should
appear among the cited sources for the questions the KB *can* answer.

By default only structural checks run (no live services needed). To run the full
end-to-end eval against a running API + Ollama, set KB_EVAL_LIVE=1 and point
KB_API_URL at the server (default http://localhost:8080).
"""

import os

import pytest

EVAL_CASES = [
    {
        "id": "auth-downloads",
        "question": "How do I require users to be logged in before they can download "
                    "occurrence records, and where is authService?",
        "answerable": True,
        "expect_sources": ["AuthService", "biocache-hub", "biocache-service"],
    },
    {
        "id": "collectory-permissions",
        "question": "What permissions does a data provider need to edit their collectory "
                    "entry? How do ContactFor, Administrator and ROLE_EDITOR relate?",
        "answerable": True,
        "expect_sources": ["User-Roles-and-Services", "collectory"],
    },
    {
        "id": "name-index-reprocess",
        "question": "After rebuilding the name index the lft/rgt values change and records "
                    "look missing in Solr unless I reprocess pipelines. Can I avoid a full reprocess?",
        "answerable": "partial",
        "expect_sources": ["Name-indexer", "Getting-Names", "bie-index"],
    },
    {
        "id": "rbac-biocache",
        "question": "How is role based access control implemented to restrict occurrence "
                    "records by user role?",
        "answerable": "partial",
        "expect_sources": ["collectory", "fieldcapture", "Biocollect"],
    },
    {
        "id": "anti-scraping",
        "question": "How do I protect biocache/BIE/spatial from aggressive scraping and bots "
                    "with nginx, robots and IP blocking?",
        "answerable": "partial",
        "expect_sources": ["spatial-livingatlas", "Secure-your-LA-infrastructure", "bie-hub"],
    },
    {
        "id": "java17-cassandra4-solr9",
        "question": "How do I upgrade biocache-service to Java 17 and migrate to Cassandra 4 "
                    "and Solr 9?",
        "answerable": False,  # no migration path documented — KB can only describe current state
        "expect_sources": [],
    },
    {
        "id": "bulk-delete-accounts",
        "question": "How can an admin bulk delete spoofed user accounts in the ALA userdetails app?",
        "answerable": False,  # userdetails admin/bulk-delete not retrievable; drifts to GBIF IPT
        "expect_sources": [],
    },
]


def test_eval_dataset_is_well_formed():
    ids = [c["id"] for c in EVAL_CASES]
    assert len(ids) == len(set(ids)), "duplicate eval case ids"
    for c in EVAL_CASES:
        assert c["question"].strip()
        assert c["answerable"] in (True, False, "partial")
        if c["answerable"] is True:
            assert c["expect_sources"], f"{c['id']}: answerable case needs expected sources"


@pytest.mark.skipif(
    os.environ.get("KB_EVAL_LIVE") != "1",
    reason="live eval against running API+Ollama; set KB_EVAL_LIVE=1 to run",
)
@pytest.mark.parametrize("case", [c for c in EVAL_CASES if c["answerable"] is True], ids=lambda c: c["id"])
def test_live_answer_cites_expected_sources(case):
    import httpx

    api = os.environ.get("KB_API_URL", "http://localhost:8080")
    resp = httpx.post(f"{api}/api/answer", json={"question": case["question"]}, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    cited = " ".join(f"{s['repo']}/{s['file']}" for s in data["sources"])
    assert any(frag in cited for frag in case["expect_sources"]), (
        f"{case['id']}: expected one of {case['expect_sources']} in cited sources, got:\n{cited}"
    )
