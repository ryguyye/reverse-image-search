from fastapi.testclient import TestClient

from selfwatch.main import app


def test_healthz_ok(temp_db):
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def test_patch_watch_toggles_active(temp_db):
    with TestClient(app) as client:
        created = client.post(
            "/api/watches",
            data={
                "name": "test",
                "cadence_minutes": "10",
                "image_url": "https://e.com/x.jpg",
            },
        ).json()
        watch_id = created["id"]
        assert created["active"] is True

        paused = client.patch(f"/api/watches/{watch_id}", json={"active": False})
        assert paused.status_code == 200
        assert paused.json()["active"] is False

        resumed = client.patch(f"/api/watches/{watch_id}", json={"active": True})
        assert resumed.json()["active"] is True


def test_patch_watch_404(temp_db):
    with TestClient(app) as client:
        resp = client.patch("/api/watches/9999", json={"active": False})
    assert resp.status_code == 404


def test_patch_watch_empty_body(temp_db):
    with TestClient(app) as client:
        created = client.post(
            "/api/watches",
            data={"name": "x", "cadence_minutes": "10", "image_url": "https://e.com/x"},
        ).json()
        resp = client.patch(f"/api/watches/{created['id']}", json={})
    assert resp.status_code == 400


def test_get_watch_matches_returns_history(temp_db):
    from selfwatch import watches
    from selfwatch.models import Match

    with TestClient(app) as client:
        created = client.post(
            "/api/watches",
            data={"name": "x", "cadence_minutes": "10", "image_url": "https://e.com/x"},
        ).json()
        watches.record_matches(
            created["id"],
            [Match(url="https://x.com/p", domain="x.com", title="hi", sources=["g"])],
        )
        resp = client.get(f"/api/watches/{created['id']}/matches")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["canonical_url"] == "https://x.com/p"
    assert body[0]["title"] == "hi"


def test_get_watch_matches_404(temp_db):
    with TestClient(app) as client:
        resp = client.get("/api/watches/9999/matches")
    assert resp.status_code == 404


def test_upload_duplicate_returns_409(temp_db, image_bytes_red):
    with TestClient(app) as client:
        first = client.post(
            "/api/watches",
            data={"name": "first", "cadence_minutes": "10"},
            files={"file": ("me.png", image_bytes_red, "image/png")},
        )
        assert first.status_code == 201

        second = client.post(
            "/api/watches",
            data={"name": "second", "cadence_minutes": "10"},
            files={"file": ("me.png", image_bytes_red, "image/png")},
        )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["existing_watch_name"] == "first"
    assert detail["distance"] == 0
    assert "force=true" in detail["hint"]


def test_upload_duplicate_with_force_succeeds(temp_db, image_bytes_red):
    with TestClient(app) as client:
        client.post(
            "/api/watches",
            data={"name": "first", "cadence_minutes": "10"},
            files={"file": ("me.png", image_bytes_red, "image/png")},
        )
        forced = client.post(
            "/api/watches",
            data={"name": "second", "cadence_minutes": "10", "force": "true"},
            files={"file": ("me.png", image_bytes_red, "image/png")},
        )
    assert forced.status_code == 201
    assert forced.json()["name"] == "second"


def test_distinct_uploads_both_succeed(temp_db, image_bytes_red, image_bytes_blue):
    with TestClient(app) as client:
        first = client.post(
            "/api/watches",
            data={"name": "red", "cadence_minutes": "10"},
            files={"file": ("red.png", image_bytes_red, "image/png")},
        )
        second = client.post(
            "/api/watches",
            data={"name": "blue", "cadence_minutes": "10"},
            files={"file": ("blue.png", image_bytes_blue, "image/png")},
        )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["image_phash"] is not None
    assert second.json()["image_phash"] is not None
    assert first.json()["image_phash"] != second.json()["image_phash"]
