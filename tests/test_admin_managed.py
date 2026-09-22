"""Admin-managed catalog: an operator's edits survive the boot-time git sync.

Runs against DATABASE_URL (a scratch Postgres; it syncs agents/ into it):

    docker run --rm -v $PWD/tests:/app/tests -e DATABASE_URL=... -e MARKETPLACE_API_KEY=k <image> \
        sh -c "pip install httpx2 && alembic upgrade head && python tests/test_admin_managed.py"
"""
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.catalog_sync import sync_specs  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402

KEY = {"X-Marketplace-Key": settings.marketplace_api_key}
c = TestClient(app)


def sync() -> None:
    with Session(engine) as s:
        sync_specs(s, "agents", allow_uneval=True)


def main() -> None:
    sync()
    slug = "bookkeeper"
    assert c.get("/v1/templates/all").status_code == 403, "the full list is operator-only"

    # 1. Hidden agents are listed for the operator, not for the store.
    assert c.patch(f"/v1/templates/{slug}", json={"is_built_in": False, "tagline": "Edited here"}, headers=KEY).status_code == 200
    every = {t["slug"]: t for t in c.get("/v1/templates/all", headers=KEY).json()["templates"]}
    shop = {t["slug"] for t in c.get("/v1/templates", headers=KEY).json()["templates"]}
    assert slug in every and slug not in shop
    assert every[slug]["admin_edited_at"] and every[slug]["version_count"] >= 1
    assert not any(t.get("is_starter") for t in every.values()), "no starter crew here"

    # 2. The next boot's sync leaves the edit alone.
    sync()
    t = c.get(f"/v1/templates/{slug}", headers=KEY).json()
    assert t["tagline"] == "Edited here" and t["is_built_in"] is False, t

    # 3. Publishing: the eval gate can't run in this image, allow_uneval still
    #    publishes (marked unpassed), and the listing follows the new version.
    latest = t["latest_version"]
    v = c.get(f"/v1/templates/{slug}/versions/{latest}", headers=KEY).json()
    major, minor, patch = (int(x) for x in latest.split("."))
    spec = {
        "slug": slug, "version": f"{major}.{minor}.{patch + 1}", "name": v["name"],
        "category": v["category"], "maintainer": v["maintainer"], "tagline": "From a new version",
        "model": v["model_routing"], "system_prompt": v["system_prompt"] + "\nNEW RULE.",
        "tools": v["tools"], "config_schema": v["config_schema"], "quality": v["quality"],
        "budget": {"default_monthly_cents": v["budget_cents"]},
    }
    r = c.post(f"/v1/templates/{slug}/versions", json=spec, headers=KEY)
    if spec["quality"].get("eval_cases"):
        assert r.status_code in (422, 503), f"strict publish must refuse: {r.status_code}"
    r = c.post(f"/v1/templates/{slug}/versions?allow_uneval=true", json=spec, headers=KEY)
    assert r.status_code == 201, r.text
    t = c.get(f"/v1/templates/{slug}", headers=KEY).json()
    assert t["latest_version"] == spec["version"] and t["tagline"] == "From a new version"
    assert t["system_prompt"].endswith("NEW RULE.")

    # 3b. A mistaken version can be deleted; the listing falls back to the
    #     newest one left.
    spec2 = dict(spec, version=f"{major}.{minor}.{patch + 2}", system_prompt="MISTAKE")
    assert c.post(f"/v1/templates/{slug}/versions?allow_uneval=true", json=spec2, headers=KEY).status_code == 201
    assert c.get(f"/v1/templates/{slug}", headers=KEY).json()["system_prompt"] == "MISTAKE"
    assert c.delete(f"/v1/templates/{slug}/versions/{spec2['version']}", headers=KEY).status_code == 204
    t = c.get(f"/v1/templates/{slug}", headers=KEY).json()
    assert t["latest_version"] == spec["version"] and t["system_prompt"].endswith("NEW RULE."), t
    assert c.delete(f"/v1/templates/{slug}/versions/9.9.9", headers=KEY).status_code == 404

    # 4. Deleted stays deleted through a sync; creating it again brings it back.
    assert c.delete(f"/v1/templates/{slug}", headers=KEY).status_code == 204
    sync()
    assert c.get(f"/v1/templates/{slug}", headers=KEY).status_code == 404, "sync resurrected a deleted agent"
    body = {"slug": slug, "name": "The Bookkeeper", "tagline": "Back", "role": "books",
            "system_prompt": "Keep the books.", "default_model": "gpt-4o-mini",
            "default_budget_cents": 1500, "category": "Finance"}
    assert c.post("/v1/templates", json=body, headers=KEY).status_code == 201
    sync()
    assert c.get(f"/v1/templates/{slug}", headers=KEY).json()["tagline"] == "Back"

    # 4b. What a new hire starts on is the admin's, and the sync leaves it be.
    assert c.get("/v1/templates/recruiter", headers=KEY).json()["hire_model"] == ""
    r = c.patch(f"/v1/templates/{slug}", json={"hire_model": "gpt-5.6-terra", "hire_image_model": "openai"}, headers=KEY)
    assert r.status_code == 200 and r.json()["hire_image_model"] == "openai"
    sync()
    t = c.get(f"/v1/templates/{slug}", headers=KEY).json()
    assert (t["hire_model"], t["hire_image_model"]) == ("gpt-5.6-terra", "openai"), t

    # 5. An untouched package is still git-managed.
    other = c.get("/v1/templates/recruiter", headers=KEY).json()
    assert other["admin_edited_at"] is None
    print("test_admin_managed: all checks passed")


if __name__ == "__main__":
    main()
