"""古籍残页转写拼接 API。

- ``POST /api/align``：提交两段含 "?"（未辨认字）的转写文本，将左段后缀与
  右段前缀做最优对齐，返回最高分对齐的原文区间、逐列对齐和拼接文本。
- ``POST /api/assemble``：提交按阅读顺序排列的 2～5 段转写，逐段复用上面的
  后缀-前缀对齐链接成最终文本，并返回与文本等长的逐字来源列表。
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from .aligner import align
from .assembler import AssemblyError, assemble

MAX_TEXT_LEN = 500  # 单段文本最大长度（残页转写通常远小于此）
MIN_SEGMENTS = 2    # /api/assemble 最少段数
MAX_SEGMENTS = 5    # /api/assemble 最多段数
MAX_TOTAL_LEN = 800  # /api/assemble 全部段合计最大长度

app = FastAPI(
    title="古籍残页转写拼接 API",
    description=(
        "对两段含 `?`（未辨认字）的古籍残页转写文本做重叠拼接："
        "只将左段后缀与右段前缀对齐，左段未参与对齐的前缀、"
        "右段未参与对齐的后缀不计分。"
    ),
    version="1.0.0",
)


class AlignRequest(BaseModel):
    """拼接请求。"""

    left: str = Field(
        ..., min_length=1, max_length=MAX_TEXT_LEN,
        description="左段转写文本，未辨认字以 ? 表示",
        examples=["学而?习之"],
    )
    right: str = Field(
        ..., min_length=1, max_length=MAX_TEXT_LEN,
        description="右段转写文本，未辨认字以 ? 表示",
        examples=["时习之不亦"],
    )


class Interval(BaseModel):
    """原文区间（下标从 0 开始，左闭右开）。"""

    start: int = Field(..., description="起点下标（含）")
    end: int = Field(..., description="终点下标（不含）")
    text: str = Field(..., description="区间原文")


class Column(BaseModel):
    """逐列对齐中的一列。"""

    left_pos: int | None = Field(..., description="左段下标；空缺为 null")
    left_char: str | None = Field(..., description="左段字形；空缺为 null")
    right_pos: int | None = Field(..., description="右段下标；空缺为 null")
    right_char: str | None = Field(..., description="右段字形；空缺为 null")
    type: str = Field(
        ...,
        description="match=相同字 / wildcard=含? / mismatch=异字 / "
                    "gap_left=左段空缺 / gap_right=右段空缺",
    )
    score: int = Field(..., description="本列得分")


class Conflict(BaseModel):
    """异字冲突：拼接时保留左段字。"""

    left_pos: int = Field(..., description="左段原文位置")
    left_char: str = Field(..., description="左段字形（拼接保留）")
    right_pos: int = Field(..., description="右段原文位置")
    right_char: str = Field(..., description="右段字形")


class ResolvedWildcard(BaseModel):
    """"?" 补字记录：以对方已知字替换。"""

    segment: str = Field(..., description="left / right")
    pos: int = Field(..., description="该段原文位置")
    resolved_char: str = Field(..., description="补入的字形")


class AlignResponse(BaseModel):
    """拼接结果。"""

    score: int = Field(..., description="最高对齐得分")
    aligned_pairs: int = Field(..., description="对齐字符对数")
    left_interval: Interval = Field(..., description="左段参与对齐的后缀区间")
    right_interval: Interval = Field(..., description="右段参与对齐的前缀区间")
    left_free_prefix: str = Field(..., description="左段未参与对齐的前缀（不计分）")
    right_free_suffix: str = Field(..., description="右段未参与对齐的后缀（不计分）")
    aligned_left: str = Field(..., description="左段对齐串（空缺以 - 表示）")
    aligned_right: str = Field(..., description="右段对齐串（空缺以 - 表示）")
    columns: list[Column] = Field(..., description="逐列对齐")
    merged: str = Field(..., description="拼接文本")
    conflicts: list[Conflict] = Field(..., description="异字冲突列表")
    resolved_wildcards: list[ResolvedWildcard] = Field(..., description="? 补字列表")


class AssembleRequest(BaseModel):
    """多段顺序拼接请求。"""

    segments: list[str] = Field(
        ..., min_length=MIN_SEGMENTS, max_length=MAX_SEGMENTS,
        description=(
            "按阅读顺序排列的转写段（2～5 段）；每段非空、最长 500 字，"
            "全部段合计不超过 800 字；未辨认字以 ? 表示"
        ),
        examples=[["孔子曰未知", "未知生焉", "生焉知死"]],
    )

    @model_validator(mode="after")
    def _validate_segments(self):
        for index, segment in enumerate(self.segments, start=1):
            if not 1 <= len(segment) <= MAX_TEXT_LEN:
                raise ValueError(f"第 {index} 段长度须在 1～{MAX_TEXT_LEN} 字之间")
        total = sum(len(segment) for segment in self.segments)
        if total > MAX_TOTAL_LEN:
            raise ValueError(f"全部段合计长度为 {total} 字，不得超过 {MAX_TOTAL_LEN} 字")
        return self


class Contributor(BaseModel):
    """单个最终字的一个原始来源：贡献它的段序号与段内下标。"""

    segment: int = Field(..., description="原始段序号（从 1 开始，按阅读顺序）")
    pos: int = Field(..., description="该段原文下标（从 0 开始）")


class AssembleResponse(BaseModel):
    """多段顺序拼接结果。"""

    text: str = Field(..., description="最终拼接文本")
    sources: list[list[Contributor]] = Field(
        ...,
        description=(
            "与 text 等长的逐字来源列表；每个字保留贡献它的所有原始段序号及"
            "原文下标，包括 ? 补字双方与异字冲突双方"
        ),
    )

    @model_validator(mode="after")
    def _sources_match_text_length(self):
        if len(self.sources) != len(self.text):
            raise ValueError("sources 必须与 text 等长")
        return self


@app.get("/", summary="服务信息")
def index():
    return {
        "name": "古籍残页转写拼接 API",
        "align": "POST /api/align",
        "assemble": "POST /api/assemble",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", summary="健康检查")
def health():
    return {"status": "ok"}


@app.post(
    "/api/align",
    response_model=AlignResponse,
    summary="拼接两段残页转写文本",
    description=(
        "计分规则：相同字 +2；`?` 与任意字配对 0；异字 -2；"
        "连续空缺首字 -3、其余每字 -1。至少一对字符对齐。"
        "同分取对齐字符对数最多者，再取左段起点最小者。"
    ),
)
def api_align(req: AlignRequest):
    return align(req.left, req.right)


@app.post(
    "/api/assemble",
    response_model=AssembleResponse,
    status_code=200,
    summary="顺序拼接 2～5 段残页转写文本",
    description=(
        "逐段复用 `/api/align` 的后缀-前缀对齐：初始文本为第 1 段，随后把当前"
        "拼接文本与下一段合并。每一步仅在**最高分大于 0 且至少有 2 对相同已知字**"
        "时继续；否则返回 422 并指出失败段序号，整次请求不产生部分结果。"
        "响应中的 `sources` 与 `text` 等长，逐字保留贡献该字的所有原始段序号及"
        "原文下标（包括 `?` 补字双方与异字冲突双方）。"
    ),
)
def api_assemble(req: AssembleRequest):
    try:
        result = assemble(req.segments)
    except AssemblyError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "failed_segment": exc.index,
                "score": exc.score,
                "known_matches": exc.known_matches,
                "min_score": 1,
                "min_known_matches": 2,
            },
        )
    return {
        "text": result["text"],
        "sources": [
            [{"segment": seg, "pos": pos} for seg, pos in refs]
            for refs in result["sources"]
        ],
    }
