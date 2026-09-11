# Phase 9 准备 — OCR 输出契约设计

> 目标：把已经存在的 HunyuanOCR 输出，正式变成 frozen Phase 3–8 可以消费的
> 稳定 HTTP 契约。**不重新做 OCR，不改 Phase 3–8 算法。**

---

## 1. 现有 OCR / bbox 能力（代码盘点）

| 位置 | 作用 |
|---|---|
| `evaluation/spatial_field_extraction/ocr.py :: call_ocr` | POST `llama.cpp /v1/chat/completions`，`model=HYVL`，官方 `spotting_hunyuan` prompt（`检测并识别图片中的文字，将文本坐标格式化输出。`），`temperature=0`，`max_tokens=8192` |
| `ocr.py :: parse_ocr_elements` | 手写字符扫描器（非 regex），把模型输出的坐标串解析成 `[{text, bbox}]` |

**HunyuanOCR 实际返回什么**（`choices[0].message.content`，一个纯字符串）：

```
PLEASE PAY THIS AMOUNT(845,117),(986,126)0000000(728,134),(786,144)$419.07(886,134),(941,145)...
```

- 格式：`TEXT(x1,y1),(x2,y2)` 一组接一组，无分隔
- 坐标：**模型已归一化到 [0,1000]**，原点左上，x 向右，y 向下
- **没有** per-element confidence / logprobs —— 探测确认 `choices[0].logprobs = None`，
  即使请求 token-level logprobs 也只是序列化字符串的 token 概率，对「某一行检测框」无意义
- 响应元数据可用：`finish_reason`（`stop` / `length`）、`usage`（token 数）、
  `timings`、`model`、`id`；**不返回图片像素尺寸**

---

## 2. Phase 3–7（+8）实际需要的最小 OCR 契约

对 8 个 frozen 文件（`spatial / structure / anchors / extract / domain /
field_semantics / phone_extract / contact_pick`）做了 dict-key 静态扫描，
再做了一次运行时验证（见 §5）。结论一致：

> **整条 frozen 管线从每个 OCR element 只读两个键：**
>
> | 键 | 类型 | 约束 |
> |---|---|---|
> | `text` | `str` | 原样文字，模型给什么就是什么 |
> | `bbox` | `[int, int, int, int]` = `[x1, y1, x2, y2]` | 归一化到 **[0,1000]**，原点左上，x→右，y→下 |

其它所有键（`kind` `band` `name` `score` `tier` `has_csz` `org_context` …）
都是管线**自己各阶段产出**的中间结果，**不来自 OCR**。

唯一还需要往下游传的 OCR 级元数据：

- `truncated`（= `finish_reason == "length"`）——Phase 3–8 用它标记
  「这份 OCR 可能被截断」。holdout 里 3 张出现过（SoCalGas / Great_American /
  DMV_Registration）；end-to-end eval 需要能区分「管线判错」和「OCR 没读全」。

`raw_content`（原始坐标串）**必须保留**：审计 + 离线重放（现在 50 张缓存就是这么用的），
也让 `parse_ocr_elements` 的解析行为可复核。

---

## 3. 最小 OCR endpoint 设计

### endpoint

```
POST /v1/ocr
```

### input（和现有 `/v1/understand-letter` 一致，二选一）

- `multipart/form-data`，字段 `file`，png / jpg / jpeg，≤ 10 MB
- 或 `application/json`：`{ "image_base64": "<...>", "mime": "image/png" }`

（webp / avif / pdf 不支持 —— llama.cpp 图像加载器已确认拒绝；客户端先转 png。）

### output schema

```jsonc
{
  "status": "ok",

  "engine": {
    "model": "HYVL",
    "task": "spotting_hunyuan",
    "coord_space": "normalized_0_1000",   // 契约核心：坐标系写死在响应里
    "origin": "top_left"
  },

  "elements": [
    { "text": "PLEASE PAY THIS AMOUNT", "bbox": [845, 117, 986, 126] },
    { "text": "$419.07",                "bbox": [886, 134, 941, 145] }
    // ... 每个元素严格 {text, bbox}，不多不少
  ],
  "element_count": 82,

  "truncated": false,               // finish_reason == "length"
  "raw_content": "PLEASE PAY THIS AMOUNT(845,117),(986,126)...",  // 原始串，审计/重放

  "image":  { "bytes": 39310, "mime": "image/png" },     // 可选，纯 debug
  "timing": { "inference_s": 32.9, "prompt_tokens": 1566, "completion_tokens": 1586 }
}
```

### 关于 §3 里点名的几个字段

| 字段 | 决定 | 理由 |
|---|---|---|
| **confidence** | **暂不放** | 当前模型 + serving 不提供。schema 里**不放**该字段（不要放 `null` 假装有）。将来换模型能给 per-line score 时，作为 `elements[i].confidence` 加进去是**加法**，不破坏现有 consumer |
| **page metadata** | **不需要** | 目标是单页信件；没有 `page` 概念。多页在别的欠账里，届时 `elements[i].page` 加字段即可 |
| **image 尺寸（像素）** | **不需要**（`image.bytes/mime` 可选） | 坐标已归一化到 [0,1000]，管线不碰像素。像素尺寸只在「把框画回原图 debug」时有用，可选 |
| **text_direction / 语言** | 不放 | 现在写死 en；管线不消费 |

### 实现

endpoint 内部 = 现有 `ocr.py::call_ocr` + `parse_ocr_elements`，**零算法改动**，
只是把它从「eval 脚本里的函数」提升成「hunyuan-service 的 HTTP 契约」。
预计 `server/api.py` 增加约 30 行，`understand-letter` 不动。

---

## 4. 如何接到 frozen Phase 3–8

```
image
  │  POST hunyuan-service:8091  /v1/ocr
  ▼
{ elements: [{text,bbox}], truncated, raw_content }      ← 稳定契约
  │  （解析已在服务端完成，client 直接拿 elements）
  ▼
field_semantics.resolve(elements)        # Phase 3 → 4 → 7   冻结
phone_extract.extract_phones(elements)   # Phase 8            冻结
contact_pick.pick_contact(phones, action, domain, sender)    # Phase 8  冻结
  ▼
最终 structured JSON
   { sender, recipient, total_amount{value,status,reason},
     payment_status{...}, due_date{...}, action{...},
     domain, domain_confidence,
     contact:{ organization, type, phone_number, confidence } }
```

Phase 3–8 的每个入口函数**入参就是 `elements`**（`extract_fields(elements)` /
`classify_domain(text,head)` / `resolve(elements)` / `extract_phones(elements)`），
`/v1/ocr` 的 `elements` 字段和 `parse_ocr_elements` 的输出**逐字节相同**（§5 已验证）。
所以接线**不需要碰任何 frozen 文件**。

### 两种落地方式（Phase 9 里选一）

| | 做法 | 何时用 |
|---|---|---|
| **A（推荐，架构对齐）** | hunyuan-service 再加 `POST /v1/understand`：内部调 `/v1/ocr` → 跑 frozen Phase 3–8 → 返回最终结构化结果。生产和 evaluation 同一条路 | 目标架构 |
| **B（Phase 9 起步够用）** | hunyuan-service 只加 `/v1/ocr`；Phase 9 eval harness 调 `/v1/ocr` 拿 elements，本地跑 frozen 管线 | 先验证 end-to-end 数字，再把编排层收进 A |

建议：**Phase 9 先做 B**（endpoint 只到 `/v1/ocr`，harness 本地编排），
拿到 end-to-end 准确率、确认和 phase5/7/8 离线数字一致后，再实现 A 的 `/v1/understand` 编排层。

---

## 5. 本地最小验证（已完成）

`evaluation/spatial_field_extraction/phase9_contract_probe.py`：
对 `Hospital_Bill.png` 做一次 **live 容器 OCR** → `parse_ocr_elements` →
`field_semantics.resolve` + `phone_extract` + `contact_pick`，
和 50 张缓存里那张（所有前序 phase 用的）结果逐字段对比。

```
element counts  live=82 cached=82  finish=stop
element shape   : {'text': 'str', 'bbox': 'list'}
sample element  : {'text': 'IF PAYING BY CREDIT CARD, FILL OUT BELOW', 'bbox': [621, 8, 895, 19]}

LIVE   fields: {sender:'Allina Health', recipient:'JANE DOE', total_amount:'419.07',
               payment_status:'unpaid', due_date:'2013-04-18', action:'pay'}
               domain: HEALTHCARE | contact: 6122629000 billing
CACHED fields: (同上)

fields identical : True
domain identical : True
contact identical: True
```

→ **契约确认：`{text, bbox}` 就是 frozen Phase 3–8 需要的全部。**

---

## 待确认后进入 Phase 9

1. `/v1/ocr` 加进 `server/api.py`（复用 `ocr.py`，≈30 行，不动 `understand-letter`）
2. 选 A 还是 B（建议先 B）
3. Phase 9 harness：图片批 → `/v1/ocr` → frozen 管线 → 和 `ground_truth_20.py` /
   `ground_truth_holdout.py` / Phase 8 GT 对比，出 end-to-end 数字，
   并和 phase5 / phase7 / phase8 的离线结果做一致性回归

**不做**：改 Phase 3–8 算法、接 Mama Helper 前端、部署 Azure。
