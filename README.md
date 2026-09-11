# letter-field-extraction

一个小型（1B）、本地跑的视觉 OCR 模型，配合确定性的空间位置规则，能不能把一封真实的美国信件读到可以抽取出结构化字段——**不用第二个 LLM、不用 regex 做语义抽取、不用语义相似度**？

**完整的当前状态、所有测试结果、待处理事项清单在 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)。** 这份 README 只是入口。

## Pipeline

```
信件照片 / PDF
  → HunyuanOCR-1B（GGUF，llama.cpp）    -- 文字 + 坐标，"spotting" prompt
  → Phase 3  位置 / 版面结构             -- 靠版面几何判断寄件人 / 收件人
  → Phase 4  信件类型分类                -- 7 类固定分类
  → Phase 7  字段语义解析                -- 按信件类型判断字段含义
  → Phase 8  联系方式 / 电话             -- 挑哪个号码、对应什么用途
  → /v1/analyze（固定 JSON 输出）
  → 确定性中文解释（前端模板拼出来的，不调模型）
  → V0 测试用 UI（webapp/）
```

> Phase 号跳着写（3 → 4 → 7 → 8）是因为**这就是现在实际在跑的那几个阶段**：Phase 1 是更早的基线、已被 Phase 3 取代；Phase 5 的内容后来并进了 Phase 7；Phase 6 从没独立存在过，编号一开始就是空的；Phase 9/10 是端到端评测和一次修复，不是流水线里单独的一步。完整的编号历史和每个 phase 的结论，看 [`PROJECT_STATUS.md`](PROJECT_STATUS.md) 里的 phase 状态表。

OCR 引擎是可替换的前端，不是这个项目的重点——`structure.py`/`field_semantics.py` 等规则代码只认一个简单的 `{text, bbox}` 契约，任何能产出这个格式的 OCR 都能换上去、用同一份 ground truth 跑分对比（参考 [`evaluation/spatial_field_extraction/RESULTS_paddleocr_vs_hunyuan_frontend.md`](evaluation/spatial_field_extraction/RESULTS_paddleocr_vs_hunyuan_frontend.md) 这个例子）。

## 测试信件覆盖了什么

50 张真实美国信件（不是合成/模板数据），横跨 Phase 4 那 7 个分类：

| 类型 | 张数 | 举例 |
|---|---:|---|
| 医疗 HEALTHCARE | 11 | 医院账单、Medicare 通知、诊所发票 |
| 保险 INSURANCE | 9 | 车险/房屋险账单、保险卡 |
| 水电/公共事业 UTILITIES_SERVICES | 8 | 电费、水费、燃气账单 |
| 银行/金融 BANKING_FINANCE | 8 | 信用卡账单、银行对账单 |
| 政府 GOVERNMENT | 7 | IRS 通知、DMV registration/违章通知 |
| 房屋/物业 HOUSING_PROPERTY | 5 | HOA 缴费单 |
| 其他 OTHER | 2 | 不属于以上几类的杂项 |

信件格式也不统一——有干净的打印体账单，也有表格密集的对账单、卡片式的保险卡、`.webp`/`.pdf` 混着的文件格式，这批数据就是全部结果（84.1% 等等）的来源，不是挑过的。

## 核心结论

| | 整体准确率（49 张真实美国信件）| 幻觉率 |
|---|---:|---:|
| **本方案**（OCR + 规则）| **84.1%** | **0.5%** |
| 让 Hunyuan 直接回答字段，一次问全部 | 41.0% | 31.5% |
| 让 Hunyuan 直接回答字段，拆开一个个问 | 44.5% | 25.0% |

完整报告：[`evaluation/spatial_field_extraction/RESULTS_native_vs_pipeline.md`](evaluation/spatial_field_extraction/RESULTS_native_vs_pipeline.md)、[`RESULTS_native_split_question.md`](evaluation/spatial_field_extraction/RESULTS_native_split_question.md)。

## 怎么跑起来

```bash
pip install -r requirements.txt
LLAMA_SERVER_URL=http://127.0.0.1:8090/v1 \
  python3 -m uvicorn server.api:app --host 127.0.0.1 --port 8091
```

打开 `http://localhost:8091/ui/` 是测试用的 UI，或者直接 `POST` 图片/PDF 到 `http://localhost:8091/v1/analyze`。需要本机已经有一个 llama-server 加载了 HunyuanOCR 的 GGUF 权重、跑在 `:8090`（权重文件没放进这个仓库，见 `.gitignore`——去 Hugging Face 下：`tencent/HunyuanOCR` / `mradermacher/HunyuanOCR-GGUF`）。

## 目录结构

```
server/api.py                          FastAPI：/v1/ocr、/v1/analyze、/v1/understand-letter（历史遗留，没在用）
webapp/index.html                      V0 测试 UI（纯静态，不用构建）
evaluation/spatial_field_extraction/   Phase 3-8 规则 + frozen_phase3/ 冻结快照 + 各种对比测试脚本
experiments/                           GPU 可行性基线 + run01 排查记录
docs/                                  OCR 接口约定、GPU 可行性报告
```

完整的 phase 历史、每一次 benchmark 的结果、当前待处理/卡住的问题，看 `PROJECT_STATUS.md`。
