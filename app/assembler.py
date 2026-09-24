"""多段残页转写的顺序拼接（逐字带来源）。

在 :func:`app.aligner.align` 的两段后缀-前缀对齐之上逐段链接：

- 初始文本为第 1 段；每一步把“当前拼接文本”作为左段、下一原始段作为右段
  调用 ``align``，复用同一套计分与并列规则；
- 仅当本步最高分 **大于 0** 且对齐中 **至少有 2 对相同已知字** 时才继续；
  否则抛出 :class:`AssemblyError`，指出失败段序号（原始段从 1 开始），
  由调用方保证整次请求不返回任何部分结果；
- 输出文本的每个字都带一个来源列表，列出贡献该字的所有
  ``(原始段序号, 段内下标)``——包括 ``?`` 补字双方与异字冲突双方；
  随着链接推进，早期段的来源会逐字透传并累积。
"""

from __future__ import annotations

from .aligner import WILDCARD, align

#: 每一步继续拼接的门槛
MIN_SCORE = 1              # 最高分必须大于 0（即 score >= 1）
MIN_KNOWN_MATCHES = 2      # 相同已知字（match）对数下限


class AssemblyError(Exception):
    """某一步不满足继续拼接的条件，整次拼接宣告失败。"""

    def __init__(self, index: int, score: int, known_matches: int):
        self.index = index              # 失败的原始段序号（从 1 开始）
        self.score = score              # 该步最高分
        self.known_matches = known_matches  # 该步相同已知字对数
        super().__init__(
            f"第 {index} 段无法与已拼接文本可靠重叠："
            f"最高分 {score}（要求 > 0），"
            f"相同已知字对 {known_matches}（要求至少 {MIN_KNOWN_MATCHES} 对）"
        )


def _merged_char(left_char: str | None, right_char: str | None) -> str:
    """对齐一列在拼接文本中采用的字形（与 aligner 的取舍一致）。"""
    if left_char is not None and left_char != WILDCARD:
        return left_char   # 相同字 / 异字（保留左字）/ 右段为 ? / 右段空缺
    return right_char      # 左段为 ?（以右字补入，双方皆 ? 时仍为 ?）/ 左段空缺


def assemble(segments: list[str]) -> dict:
    """按阅读顺序把多段转写链接为一段，返回最终文本与逐字来源。

    ``sources[k]`` 为最终文本第 k 字的全部来源 ``(段序号, 段内下标)``；
    段序号从 1 开始，段内下标从 0 开始。
    """
    text = segments[0]
    sources: list[list[tuple[int, int]]] = [
        [(1, pos)] for pos in range(len(text))
    ]

    for offset in range(1, len(segments)):
        seg_no = offset + 1
        right = segments[offset]
        result = align(text, right)

        known_matches = sum(
            1 for col in result["columns"] if col["type"] == "match"
        )
        if result["score"] < MIN_SCORE or known_matches < MIN_KNOWN_MATCHES:
            raise AssemblyError(seg_no, result["score"], known_matches)

        start = result["left_interval"]["start"]
        end_j = result["right_interval"]["end"]

        # 对齐区逐字合并：字形按 aligner 规则取舍，来源则收编双方。
        mid_chars: list[str] = []
        mid_sources: list[list[tuple[int, int]]] = []
        for col in result["columns"]:
            lp, rp = col["left_pos"], col["right_pos"]
            contributors: list[tuple[int, int]] = []
            if lp is not None:
                # 对齐只触及左段后缀；透传该字此前累积的全部来源
                assert lp >= start
                contributors.extend(sources[lp])
            if rp is not None:
                # 新段对该字的贡献：? 补字位、异字位同样保留
                contributors.append((seg_no, rp))
            mid_chars.append(_merged_char(col["left_char"], col["right_char"]))
            mid_sources.append(contributors)

        # 左段自由前缀原样保留；右段自由后缀为仅属新段的新字
        text = text[:start] + "".join(mid_chars) + right[end_j:]
        sources = (
            sources[:start]
            + mid_sources
            + [[(seg_no, pos)] for pos in range(end_j, len(right))]
        )
        assert len(text) == len(sources)

    return {"text": text, "sources": sources}
