"""API 接口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_align_endpoint():
    resp = client.post("/api/align", json={"left": "学而?习之", "right": "时习之不亦"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 4
    assert data["merged"] == "学而时习之不亦"
    assert data["left_interval"] == {"start": 2, "end": 5, "text": "?习之"}
    assert data["right_interval"] == {"start": 0, "end": 3, "text": "时习之"}
    assert len(data["columns"]) == 3
    assert data["resolved_wildcards"] == [
        {"segment": "left", "pos": 2, "resolved_char": "时"}
    ]


def test_align_endpoint_with_conflict():
    resp = client.post("/api/align", json={"left": "甲乙丙丁", "right": "丙戌戊"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["merged"] == "甲乙丙丁戊"
    assert data["conflicts"] == [
        {"left_pos": 3, "left_char": "丁", "right_pos": 1, "right_char": "戌"}
    ]


def test_empty_segment_rejected():
    resp = client.post("/api/align", json={"left": "", "right": "abc"})
    assert resp.status_code == 422
    resp = client.post("/api/align", json={"left": "abc", "right": ""})
    assert resp.status_code == 422


def test_missing_field_rejected():
    resp = client.post("/api/align", json={"left": "abc"})
    assert resp.status_code == 422
