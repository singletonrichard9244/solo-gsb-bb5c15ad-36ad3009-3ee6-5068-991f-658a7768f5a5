# 古籍残页转写拼接 API

提交含 `?`（未辨认字）的古籍残页转写文本，API 将**左段后缀与右段前缀**做最优重叠对齐：

- `POST /api/align`：拼接**两段**转写，返回最高分对齐的原文区间、逐列对齐和拼接文本；
- `POST /api/assemble`：按阅读顺序拼接 **2～5 段**转写，逐段复用同一对齐算法，
  返回最终文本和与其等长的**逐字来源列表**。

## 快速开始

单条命令启动（依赖已纳入镜像构建）：

```bash
docker compose up --build
```

- **接口地址**：http://localhost:8000
- **端口**：8000
- **交互式接口文档（Swagger UI）**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/health

## 接口说明

### `POST /api/align`

请求体：

```json
{
  "left": "学而?习之",
  "right": "时习之不亦"
}
```

- `left`、`right`：必填，非空字符串（单段最长 500 字），未辨认字以 `?` 表示。

响应示例：

```json
{
  "score": 4,
  "aligned_pairs": 3,
  "left_interval": { "start": 2, "end": 5, "text": "?习之" },
  "right_interval": { "start": 0, "end": 3, "text": "时习之" },
  "left_free_prefix": "学而",
  "right_free_suffix": "不亦",
  "aligned_left": "?习之",
  "aligned_right": "时习之",
  "columns": [
    { "left_pos": 2, "left_char": "?", "right_pos": 0, "right_char": "时", "type": "wildcard", "score": 0 },
    { "left_pos": 3, "left_char": "习", "right_pos": 1, "right_char": "习", "type": "match", "score": 2 },
    { "left_pos": 4, "left_char": "之", "right_pos": 2, "right_char": "之", "type": "match", "score": 2 }
  ],
  "merged": "学而时习之不亦",
  "conflicts": [],
  "resolved_wildcards": [
    { "segment": "left", "pos": 2, "resolved_char": "时" }
  ]
}
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `score` | 最高对齐得分 |
| `aligned_pairs` | 对齐字符对数 |
| `left_interval` / `right_interval` | 左/右段参与对齐的原文区间（下标从 0 开始，左闭右开） |
| `left_free_prefix` / `right_free_suffix` | 未参与对齐、不计分的左段前缀 / 右段后缀 |
| `aligned_left` / `aligned_right` | 对齐串（空缺以 `-` 表示） |
| `columns` | 逐列对齐：`type` 为 `match`（相同字）/ `wildcard`（含 `?`）/ `mismatch`（异字）/ `gap_left`（左段空缺）/ `gap_right`（右段空缺），`score` 为本列得分 |
| `merged` | 拼接文本 |
| `conflicts` | 异字冲突列表：保留左段字，并列出双方原文位置及字形 |
| `resolved_wildcards` | `?` 补字列表：以对方已知字替换 |

调用示例：

```bash
curl -X POST http://localhost:8000/api/align \
  -H "Content-Type: application/json" \
  -d '{"left": "学而?习之", "right": "时习之不亦"}'
```

### `POST /api/assemble`

按阅读顺序提交 2～5 段转写（每段最长 500 字、全部段合计不超过 800 字），
逐段复用 `/api/align` 的后缀-前缀对齐：初始文本为第 1 段，随后把**当前拼接文本**
与下一段合并。

- **继续条件**：每一步仅当本步最高分 **大于 0** 且对齐中**至少有 2 对相同已知字**
  （`match` 列）时才继续；否则返回 **422** 并指出失败段序号，整次请求不产生部分结果。
- **逐字来源**：响应的 `sources` 与 `text` 等长，`sources[k]` 列出贡献最终文本第 k 字的
  所有原始段序号（`segment`，从 1 开始）及原文下标（`pos`，从 0 开始）——
  包括 `?` 补字双方与异字冲突双方；来源随链接逐字节累积。

请求体：

```json
{
  "segments": ["孔子曰未知", "未知生焉", "生焉知死"]
}
```

响应示例：

```json
{
  "text": "孔子曰未知生焉知死",
  "sources": [
    [ { "segment": 1, "pos": 0 } ],
    [ { "segment": 1, "pos": 1 } ],
    [ { "segment": 1, "pos": 2 } ],
    [ { "segment": 1, "pos": 3 }, { "segment": 2, "pos": 0 } ],
    [ { "segment": 1, "pos": 4 }, { "segment": 2, "pos": 1 } ],
    [ { "segment": 2, "pos": 2 }, { "segment": 3, "pos": 0 } ],
    [ { "segment": 2, "pos": 3 }, { "segment": 3, "pos": 1 } ],
    [ { "segment": 3, "pos": 2 } ],
    [ { "segment": 3, "pos": 3 } ]
  ]
}
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `text` | 最终拼接文本 |
| `sources` | 与 `text` 等长的逐字来源列表；每个字保留贡献它的所有 `{segment, pos}`，含 `?` 补字双方与异字冲突双方 |

调用示例：

```bash
curl -X POST http://localhost:8000/api/assemble \
  -H "Content-Type: application/json" \
  -d '{"segments": ["孔子曰未知", "未知生焉", "生焉知死"]}'
```

某一步不满足继续条件时返回 422，指出失败段序号，且不含任何部分结果：

```bash
curl -X POST http://localhost:8000/api/assemble \
  -H "Content-Type: application/json" \
  -d '{"segments": ["孔子曰未知", "未知生焉", "xxxx"]}'
```

```json
{
  "detail": {
    "message": "第 3 段无法与已拼接文本可靠重叠：最高分 -2（要求 > 0），相同已知字对 0（要求至少 2 对）",
    "failed_segment": 3,
    "score": -2,
    "known_matches": 0,
    "min_score": 1,
    "min_known_matches": 2
  }
}
```

段数不在 2～5、存在空段、单段超过 500 字或合计超过 800 字时，同样返回 422（参数校验错误）。

## 计分与并列规则

- 相同字 **+2**；`?` 与任意字配对 **0**；异字 **-2**；
- 连续空缺：首字 **-3**，其余每字 **-1**；
- 只将左段后缀与右段前缀对齐；左段未参与对齐的前缀、右段未参与对齐的后缀**不计分**；
- 对齐区**至少包含一对字符**；
- 同分并列时，取**对齐字符对数最多**者；仍并列，取**左段起点最小**者。

## 拼接规则

- `?` 以对方已知字替换（双方均为 `?` 时保留 `?`）；
- 异字保留左段字，并在 `conflicts` 中列出双方原文位置及字形。

`/api/assemble` 逐段链接时沿用以上规则：当前拼接文本作为左段、下一段作为右段；
`?` 补字位与补入字所在的对方位置、异字冲突的双方位置，都会作为来源保留在 `sources` 中。

## 本地开发（不使用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 运行测试

```bash
pip install -r requirements.txt requirements-dev.txt
pytest
```

## 项目结构

```
app/
  aligner.py   # 核心算法：后缀-前缀重叠对齐（仿射空缺罚分 DP + 回溯）
  assembler.py # 多段顺序链接：逐段复用 align 并维护逐字来源
  main.py      # FastAPI 接口与请求/响应模型（/api/align、/api/assemble）
tests/         # 算法与接口测试
Dockerfile     # 镜像构建（含依赖安装）
docker-compose.yml
```
