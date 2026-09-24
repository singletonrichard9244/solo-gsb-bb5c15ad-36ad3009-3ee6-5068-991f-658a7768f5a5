"""API 接口测试。"""

import pytest
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


def test_assemble_success():
    resp = client.post(
        "/api/assemble",
        json={"segments": ["孔子曰未知", "未知生焉", "生焉知死"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "孔子曰未知生焉知死"
    assert len(data["sources"]) == len(data["text"])
    assert data["sources"][3] == [
        {"segment": 1, "pos": 3},
        {"segment": 2, "pos": 0},
    ]
    assert data["sources"][5] == [
        {"segment": 2, "pos": 2},
        {"segment": 3, "pos": 0},
    ]


def test_assemble_wildcard_and_mismatch_sources():
    # ? 补字：保留 ? 位与补入字来源
    resp = client.post(
        "/api/assemble", json={"segments": ["学而?习之", "时习之不亦"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "学而时习之不亦"
    assert data["sources"][2] == [
        {"segment": 1, "pos": 2},
        {"segment": 2, "pos": 0},
    ]

    # 异字冲突：保留左段字，来源保留冲突双方
    resp = client.post(
        "/api/assemble", json={"segments": ["丙戌甲亥", "丙戌丁亥"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "丙戌甲亥"
    assert data["sources"][2] == [
        {"segment": 1, "pos": 2},
        {"segment": 2, "pos": 2},
    ]


def test_assemble_failure_returns_422_with_segment_index():
    resp = client.post(
        "/api/assemble",
        json={"segments": ["孔子曰未知", "未知生焉", "xxxx"]},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["failed_segment"] == 3
    assert detail["min_score"] == 1
    assert detail["min_known_matches"] == 2
    # 失败响应中不含任何部分结果
    assert "text" not in detail and "sources" not in detail


def test_assemble_failure_at_second_segment():
    resp = client.post("/api/assemble", json={"segments": ["abc", "xyz"]})
    assert resp.status_code == 422
    assert resp.json()["detail"]["failed_segment"] == 2


@pytest.mark.parametrize(
    "segments",
    [
        ["abc"],                                   # 少于 2 段
        ["a", "a", "a", "a", "a", "a"],           # 超过 5 段
        [],                                        # 空列表
        ["abc", ""],                               # 存在空段
        ["a" * 501, "aa"],                         # 单段超过 500 字
        ["a" * 401, "a" * 400],                    # 合计超过 800 字
    ],
)
def test_assemble_validation_errors(segments):
    resp = client.post("/api/assemble", json={"segments": segments})
    assert resp.status_code == 422


def test_assemble_accepts_boundary_sizes():
    # 5 段、每段非空、合计 800 字（400+100+2+2+296）：通过参数校验且各步均可链接
    resp = client.post(
        "/api/assemble",
        json={"segments": ["a" * 400, "a" * 100, "aa", "aa", "a" * 296]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "a" * 400


def test_assemble_missing_field_rejected():
    resp = client.post("/api/assemble", json={})
    assert resp.status_code == 422


def test_index_lists_assemble():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["assemble"] == "POST /api/assemble"
