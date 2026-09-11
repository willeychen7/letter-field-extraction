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

### Phase 3-8 分别在做什么

| Phase | 代码 | 干什么 | 怎么判断 |
|---|---|---|---|
| **3 · 位置/版面结构** | `structure.py`/`extract.py`/`anchors.py` | 从 OCR 给的坐标里找出寄件人、收件人是哪一块 | 看版面几何：找左对齐、连续堆叠的「姓名/街道/城市州邮编」块。寄件人按 S1（顶部信头）>S2（关键词锚点+机构名）>S3（位置像机构）的优先级判断；收件人按 R1（有"To/收件人"标签）>R3（同一个名字在两块地方重复出现）>R2（一整块没标签但位置对）>R4（只有部分地址）的优先级判断。位置证据配合一个很小的关键词表（不是 regex），比如"Attn""Dear"这类锚点词 |
| **4 · 信件类型分类** | `domain.py` | 判断这封信属于医疗/保险/银行/政府/水电/房屋/其他 7 类中的哪一类 | 给发件机构名、信件主题关键词、版面特征打分，分最高的类别胜出；最高分和第二高分的差距（`domain_gap`）就是这次分类的置信度 |
| **7 · 字段语义解析** | `field_semantics.py` | 判断金额到底是"要付多少"还是"欠费"还是"这次报销了多少"，判断这封信要收件人做什么、什么时候前 | 一张按信件类型写死的规则表，信件类型（Phase 4 的结果）只是拿来约束"这个字段该怎么理解"，不是直接拿来当答案。寄件人/收件人/到期日是从 Phase 3 原样传过来的，不重新判断。每个字段都带一个状态：判断出来了 / 这封信里这个字段本来就不适用 / 证据不够不敢说 |
| **8 · 联系方式/电话** | `phone_extract.py`+`contact_pick.py` | 一封信里可能印着好几个电话号码，判断哪一个是收件人真正该打的那个 | 先找出所有长得像电话号码的文本，再按"这个号码和信件要办的事有没有关系""周围文字提示的用途""在版面上的位置"打分，挑最高分的那个；分数不够高，宁可返回空，不瞎猜——在 49 封信的测试里 0 次猜错号码 |

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

这个仓库本身只是规则代码 + API + UI，不含模型权重、也不含 OCR 引擎本身
（见 `.gitignore`）。要跑起来需要另外装两样东西：**llama.cpp**（跑模型的
推理引擎）和 **HunyuanOCR 的权重文件**（两个 `.gguf`）。下面是从零开始的
步骤。

### 1. 克隆这个仓库

```bash
git clone https://github.com/willeychen7/letter-field-extraction.git
cd letter-field-extraction
```

### 2. 装 llama.cpp（跑模型用的引擎，不是这个仓库的一部分）

需要一个支持 `hunyuan_vl` 架构（视觉模型）的**较新版本**，太旧的版本认不出
这个模型。

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --target llama-server -j
```

编译完成后，`llama-server` 这个可执行文件在 `build/bin/llama-server`。

### 3. 下载 HunyuanOCR 权重（两个文件，一共约 2GB）

去 Hugging Face 下 `mradermacher/HunyuanOCR-GGUF`（或官方
`tencent/HunyuanOCR`），要**两个文件**：

- `HunyuanOCR-Q8_0.gguf` —— 主模型
- `mmproj-HunyuanOCR-Q8_0.gguf` —— 视觉编码器，负责"看懂"图片，缺这个模型
  就只能处理纯文字、不能读图

存到本地任意目录，比如 `models/`（这个目录已经在 `.gitignore` 里，不会被
误传进 git）。

### 4. 启动 llama-server（跑在 `:8090`）

```bash
./llama.cpp/build/bin/llama-server \
  -m models/HunyuanOCR-Q8_0.gguf \
  --mmproj models/mmproj-HunyuanOCR-Q8_0.gguf \
  --ctx-size 8192 --parallel 1 \
  --host 127.0.0.1 --port 8090
```

有 NVIDIA GPU 的话可以加 `-ngl 99` 把模型全部丢到显卡上跑，会快很多（见
[`docs/PHASE9B_GPU_FEASIBILITY.md`](docs/PHASE9B_GPU_FEASIBILITY.md)）—
但目前 GPU 上跑出来的输出格式还没验证过能不能被这条流水线用，纯 CPU 是目
前唯一确认可用的跑法，见 `PROJECT_STATUS.md` 里的已知瓶颈。`--ctx-size` 要
和 `--parallel` 搭配着看：llama-server 实际会把 `--ctx-size` 除以
`--parallel` 分给每个并发槽位，槽位太小会在处理大图时报"exceeds context
size"，所以本地单人测试用 `--parallel 1` 最简单。

### 5. 装这个仓库的 Python 依赖，启动 API

```bash
pip install -r requirements.txt
LLAMA_SERVER_URL=http://127.0.0.1:8090/v1 \
  python3 -m uvicorn server.api:app --host 127.0.0.1 --port 8091
```

### 6. 打开测试 UI，或者直接调 API

打开浏览器访问 `http://localhost:8091/ui/`，拍照/上传一张信件照片就能看到
结果；或者跳过 UI，直接 `POST` 图片/PDF 到
`http://localhost:8091/v1/analyze`，拿到结构化 JSON。

### 或者：用 Docker

仓库根目录的 [`Dockerfile`](Dockerfile) 只打包这个仓库自己（API + Phase
3-8 规则 + UI），**不包含 llama-server**——第 2-4 步的 llama-server 仍然
需要单独装好、单独跑着（容器或宿主机上都行）。装好之后用
[`docker-run.sh`](docker-run.sh) 一键构建并启动这个仓库的镜像，把它接到
已经在跑的 llama-server 上（脚本里有把两个容器连到同一个 Docker 网络的
逻辑）；如果 llama-server 跑在宿主机而不是容器里，把 `LLAMA_SERVER_URL`
改成 `http://host.docker.internal:8090/v1` 即可。

## 目录结构

```
server/api.py                          FastAPI：/v1/ocr、/v1/analyze、/v1/understand-letter（历史遗留，没在用）
webapp/index.html                      V0 测试 UI（纯静态，不用构建）
evaluation/spatial_field_extraction/   Phase 3-8 规则 + frozen_phase3/ 冻结快照 + 各种对比测试脚本
experiments/                           GPU 可行性基线 + run01 排查记录
docs/                                  OCR 接口约定、GPU 可行性报告
```

完整的 phase 历史、每一次 benchmark 的结果、当前待处理/卡住的问题，看 `PROJECT_STATUS.md`。
