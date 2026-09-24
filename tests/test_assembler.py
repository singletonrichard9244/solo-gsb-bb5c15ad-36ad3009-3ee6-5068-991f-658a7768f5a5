"""多段顺序拼接（assembler）测试。"""

import pytest

from app.assembler import AssemblyError, assemble


def test_three_segments_chained():
    # 第 1 步：未/未、知/知；第 2 步：生/生、焉/焉
    r = assemble(["孔子曰未知", "未知生焉", "生焉知死"])
    assert r["text"] == "孔子曰未知生焉知死"
    assert r["sources"] == [
        [(1, 0)],                                   # 孔
        [(1, 1)],                                   # 子
        [(1, 2)],                                   # 曰
        [(1, 3), (2, 0)],                           # 未（两段重叠）
        [(1, 4), (2, 1)],                           # 知
        [(2, 2), (3, 0)],                           # 生（来源跨第 2、3 段）
        [(2, 3), (3, 1)],                           # 焉
        [(3, 2)],                                   # 知
        [(3, 3)],                                   # 死
    ]


def test_sources_length_equals_text_length():
    r = assemble(["孔子曰未知", "未知生焉", "生焉知死"])
    assert len(r["sources"]) == len(r["text"])


def test_wildcard_fill_keeps_both_sites():
    # "?" 位与补入字所在的对方位置都保留为来源
    r = assemble(["学而?习之", "时习之不亦"])
    assert r["text"] == "学而时习之不亦"
    assert r["sources"][2] == [(1, 2), (2, 0)]      # 时：? 位 + 右段"时"
    assert r["sources"][3] == [(1, 3), (2, 1)]      # 习
    assert r["sources"][6] == [(2, 4)]              # 亦：仅右段新字


def test_mismatch_keeps_left_char_with_both_sources():
    # 甲/丁 冲突：保留左段"甲"，来源保留冲突双方
    r = assemble(["丙戌甲亥", "丙戌丁亥"])
    assert r["text"] == "丙戌甲亥"
    assert r["sources"][2] == [(1, 2), (2, 2)]
    assert r["sources"][3] == [(1, 3), (2, 3)]


def test_overhang_right_prefix_new_char():
    # 右段从左侧探出："a" 为仅属第 2 段的新字
    r = assemble(["bc", "abc"])
    assert r["text"] == "abc"
    assert r["sources"] == [
        [(2, 0)],
        [(1, 0), (2, 1)],
        [(1, 1), (2, 2)],
    ]


def test_provenance_accumulates_through_chain():
    # 同一批字在多次重叠中持续累积来源（第 3 段再次贡献"生焉"）
    r = assemble(["未生", "未生焉", "生焉"])
    assert r["text"] == "未生焉"
    assert r["sources"][0] == [(1, 0), (2, 0)]
    assert r["sources"][1] == [(1, 1), (2, 1), (3, 0)]
    assert r["sources"][2] == [(2, 2), (3, 1)]


def test_failure_at_second_segment_raises():
    with pytest.raises(AssemblyError) as exc:
        assemble(["abc", "xyz"])
    assert exc.value.index == 2
    assert exc.value.score <= 0
    assert exc.value.known_matches < 2


def test_failure_at_later_segment_reports_its_index():
    with pytest.raises(AssemblyError) as exc:
        assemble(["孔子曰未知", "未知生焉", "xxxx"])
    assert exc.value.index == 3
    assert exc.value.score <= 0
    assert exc.value.known_matches < 2


def test_positive_score_with_two_matches_still_rejected():
    # 有 2 对相同已知字，但空缺罚分使最高分为 -1（不大于 0）
    with pytest.raises(AssemblyError) as exc:
        assemble(["abxyz", "abmn"])
    assert exc.value.index == 2
    assert exc.value.known_matches == 2
    assert exc.value.score <= 0


def test_single_match_rejected_even_if_score_positive():
    # "abcx" 与 "xyz" 仅 1 对相同已知字（x）
    with pytest.raises(AssemblyError) as exc:
        assemble(["abc", "abcx", "xyz"])
    assert exc.value.index == 3
    assert exc.value.known_matches < 2
