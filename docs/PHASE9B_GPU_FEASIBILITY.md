# HunyuanOCR GPU 部署可行性评估

> 目的：回答「把现在这套 HunyuanOCR 从 CPU Docker 搬到 GPU，能不能达到可用速度和稳定性」。
> **只调查，不实施。不改 Phase 3–8，不改 OCR prompt / 算法 / GGUF 模型。**

变的只有 llama.cpp 的**运行时**（CPU build → CUDA build）和**宿主机**（Mac Docker → GPU）。
`ocr.py` / `parse_ocr_elements` / `/v1/ocr` / `spotting_hunyuan` prompt / `hunyuan-service`
全部原样，只把 `LLAMA_SERVER_URL` 指向 GPU 上的 llama 端点。

---

## 事实盘点（实测）

| 项 | 值 |
|---|---|
| 文本模型 `HunyuanOCR-Q8_0.gguf` | **561 MB**，arch `hunyuan_vl`，24 层 / hidden 1024 / 16 head，训练 ctx 32768，≈1B 参数，Q8_0 |
| 视觉编码器 `mmproj-HunyuanOCR-Q8_0.gguf` | **699 MB**，arch `clip`，**image_size 2048**（高分辨率视觉，prefill 重），27 层 |
| **权重合计** | **≈ 1.26 GB** |
| 当前容器镜像 | `ghcr.io/ggml-org/llama.cpp:server` — **arm64/linux, 298 MB**，纯 CPU build（Docker Desktop 的 Linux VM，无 Metal、无 CUDA）→ 这就是慢和崩的根因 |
| 当前 llama 配置 | `--host 0.0.0.0 --port 8090`，默认 `n_slots=4, n_ctx_slot=32768`（对 OCR 严重过配，是内存压力来源） |
| Phase 9 实测 OCR 延迟 | 中位 61s / 均值 74s / 最大 294s；50 张里崩 2 次，`SoCalGas` 完全失败 |

---

## 逐条回答

### 1. HunyuanOCR-1B + GGUF + llama.cpp 是否适合 GPU server

**适合，而且是最省事的路径。** llama.cpp 官方就有 CUDA 版：镜像 `ghcr.io/ggml-org/llama.cpp:server-cuda`
（或自己 `-DGGML_CUDA=ON` 编）。近版本 llama.cpp 的 CUDA build **同时把 clip/mmproj 视觉编码器也放 GPU**。
部署改动最小：同一条 `docker run`，镜像换 `-cuda` tag，加 `--gpus all` 和 `-ngl 99`（全层 offload），
模型 volume 挂载不变。

> ⚠️ **唯一需要先验证的点**：`hunyuan_vl` 是相对新的架构，当前在 CPU ARM build 上跑通。
> 换到 `server-cuda` 前，先花 ~30 分钟在一台带 GPU 的机器上跑一张 `AAA_insurance_Bill.png`
> 做 smoke test，确认 CUDA build 支持这个 mmproj。风险不大（同一份代码库、同期），但要确认。

### 2. Q8_0 + mmproj 需要多少显存

| 组成 | 显存 |
|---|---|
| 权重（Q8_0 全 offload） | ≈ 1.3 GB |
| KV cache —— **按当前 4×32768 配置** | ≈ 13 GB（荒谬地过大） |
| KV cache —— **OCR 合理配置** `--ctx-size 8192 --parallel 2` | ≈ 0.4–0.8 GB |
| 视觉 prefill 计算缓冲（2048px 图，瞬时） | ≈ 1–2 GB |
| CUDA / 运行时开销 | ≈ 0.5–1 GB |
| **合理总量** | **≈ 4–6 GB** |

**结论：任何一块 ≥8 GB 的现代 NVIDIA GPU 都够**，而且富余。不需要大卡。
（必须把 `n_ctx` 从 32768 调回 8192 左右、`--parallel` 调到 2–4 —— 这是 llama.cpp 启动参数，不是算法/prompt。）

### 3. 哪种 GPU 最适合

模型太小，选择很宽。按性价比：

| GPU | 显存 | 适合度 | 备注 |
|---|---|---|---|
| **NVIDIA L4** | 24 GB | ★★★★★ | 新、省电、云上便宜、专为推理。首选 |
| **NVIDIA T4** | 16 GB | ★★★★☆ | 到处都有、最便宜、Azure ACA serverless GPU 就是它。够用 |
| **NVIDIA A10 / A10G** | 24 GB | ★★★★☆ | 比 L4 快一点，贵一点 |
| RTX 4090 / 4080 / 3060 12G | 8–24 GB | ★★★★☆ | 自租云 GPU（RunPod/Vast）最便宜，但企业/Azure 场景不用消费卡 |
| A100 / H100 | 40–80 GB | ★☆☆☆☆ | **完全过剩**，纯浪费钱 |

**推荐：L4（生产）或 T4（够用且最省）。**

### 4. llama.cpp Docker 能不能直接用 GPU

**能，标准做法。** 宿主机装 NVIDIA driver + NVIDIA Container Toolkit，然后：

```
docker run -d --name hunyuan-llama --gpus all \
  -v /path/to/models:/models \
  ghcr.io/ggml-org/llama.cpp:server-cuda \
  -m /models/HunyuanOCR-Q8_0.gguf --mmproj /models/mmproj-HunyuanOCR-Q8_0.gguf \
  -ngl 99 --ctx-size 8192 --parallel 3 --host 0.0.0.0 --port 8090
```

`hunyuan-service` 侧零改动。

### 5. Azure Container Apps GPU 适不适合；不合适的话 Azure 哪个服务更合适

**ACA serverless GPU 适合，是这个 workload 在 Azure 上的最佳落点** —— 前提是选到有 GPU workload profile 的区域（如 West US 3、Australia East 等，region 受限，需查）。

- workload 是 **GPU-bound 的视觉 prefill + 小 LM 解码**，正是 GPU 该干的活。
- **scale-to-zero** 契合「老人偶尔上传」的突发流量 —— 闲时不花钱。
- **代价：冷启动** = 容器启动 + 加载 1.3 GB 权重 ≈ **10–30s**（T4）。第一张图慢，之后快。
  可设 **最小 1 个常驻 replica** 消除冷启动，但那就一直在计费。
- 模型放法：烤进镜像，或挂 Azure Files。

**如果 ACA GPU 区域不可用 / 冷启动不可接受**，按优先级：

| 方案 | 说明 |
|---|---|
| **Azure Container Instances (ACI) + GPU（T4）** | 比 ACA 简单，无 scale-to-zero，常开计费，启动 ~1–2 min |
| **Azure VM `Standard_NC4as_T4_v3`（整块 T4 16GB）** | 最可预测、最可控，需自己装 driver + toolkit，ops 多一点 |
| **Azure VM `Standard_NV6ads_A10_v5`（1/6 A10）** | 最便宜的常开 GPU，显存 4–8 GB 刚好够，PAYG ≈ $150/月 |

**明确不要**：Azure App Service / ACA CPU / Functions —— 那是把现在的 CPU 问题原样搬到云上。
**也不要** Azure ML managed endpoint —— 对一个 llama.cpp server 是过度封装。

### 6. GPU server 能不能支撑多用户连续上传

**能。** llama.cpp server 自带 `--parallel N` + continuous batching。

| GPU | 持续吞吐（单张 ~5s） | 并发 |
|---|---|---|
| T4 | ≈ 5–15 张/分钟 | `--parallel 3` 舒适 |
| L4 / A10 | ≈ 15–40 张/分钟 | `--parallel 4–6` |

瓶颈是 2048px 图的视觉 prefill 吞吐，不是 LM。对「华人老人偶尔拍一张信」这种量级**绰绰有余**；
真不够就横向加 replica。

### 7. 单张 OCR latency 相比 CPU-only 能改善多少

| | 中位 | 典型范围 | 最坏（多栏大账单） |
|---|---|---|---|
| **当前 CPU Docker** | 61s | 30–150s | 294s（+ 崩溃 / 失败） |
| **T4 GPU** | **~4–6s** | 3–10s | ~12–18s |
| **L4 / A10 GPU** | **~2–4s** | 2–6s | ~8–12s |

**≈ 10–20 倍加速**，稳稳落进「10–20s 可用」目标，通常更快。`SoCalGas` 那张会在几秒内跑完。

### 8. 能不能解决容器崩溃 / 稳定性问题

**能，多重原因：**
1. 单次推理从 100–300s 缩到几秒 → 资源只被短暂占用，竞争急剧下降。
2. GPU 有独立显存 + 合理 `--ctx-size 8192 --parallel 2–4` → 不再 OOM（当前是 7.7 GB 的 Docker VM 里塞 4×32K KV cache 撑爆）。
3. GPU 不吃宿主 CPU / RAM，不会热节流。

预期：**当前「每 ~12–15 张重请求崩一次」的现象消失**，`SoCalGas` 这类大图不再失败。
（还是建议保留 `--restart unless-stopped` 兜底。）

### 9. 成本区间

| 场景 | 方案 | 估算 |
|---|---|---|
| **只做 eval / 偶尔跑 benchmark** | 云 GPU 按小时租（L4/T4 spot） | **单次 ~$0.30–0.60**（跑完 50 张约 10–20 分钟） |
| **低 / 突发生产流量**（老人偶尔上传，~1k 张/月） | Azure ACA serverless GPU（T4），scale-to-zero | **~$10–40/月**（含少量常驻分钟避冷启动）；纯按用量甚至 <$15 |
| **中等常开**（要低延迟、无冷启动） | Azure `NV6ads_A10_v5`（1/6 A10）常开 | **~$150/月** |
| | Azure `NC4as_T4_v3`（整块 T4）PAYG | **~$385/月**；1 年预留 ~$230/月 |
| | 云 GPU 租用（L4/T4）常开 on-demand | **~$220–650/月**；spot ~$110–300/月 |

数字为量级估计，未含出网流量 / 存储 / 汇率波动，正式报价以 Azure Pricing Calculator 为准。

---

## 方案比较：当前 CPU Docker vs GPU Server vs Azure GPU

| | **当前 CPU Docker（Mac）** | **GPU Server（自租云 / 自有 GPU 机）** | **Azure GPU（ACA serverless GPU / T4）** |
|---|---|---|---|
| **速度** | ✗ 中位 61s，最坏 294s。不可用 | ✓✓ 中位 2–6s（L4/T4）。目标达成，通常更好 | ✓ 热时 3–8s；**冷启动首张 +10–30s** |
| **稳定性** | ✗ 50 张崩 2 次，1 张彻底失败 | ✓✓ 短推理 + 充足显存 + 合理 ctx → 崩溃消除 | ✓✓ 同左；scale-to-zero 时靠健康探针 + 冷启动 |
| **多用户并发** | ✗ 单请求就把上游打挂 | ✓✓ `--parallel` + 批处理，T4 ~10 张/分，可横向扩 | ✓ 同左；ACA 自动按并发扩 replica |
| **成本** | 电费（但不可用） | eval：单次 <$1；常开 $150–650/月 | 突发：**$10–40/月**（最省）；常驻 replica 另计 |
| **部署难度** | 已在跑 | **低** —— 换 `-cuda` 镜像 + `--gpus all -ngl 99`，~30 min（+ driver/toolkit 若新机 ~2h） | **中** —— GPU region、镜像推 ACR、`az containerapp` 配置、模型放 Azure Files、冷启动调优，~半天 |
| **可预测性 / 运维** | — | 自租：便宜但要自己管机器 / spot 被抢风险 | 托管、少运维、按用量、和后续 Azure 架构一致 |
| **Phase 3–8 / OCR 算法** | — | **不动** | **不动** |

---

## 结论（供决策，不是实施）

1. **GPU 能把 OCR 从「几十秒 + 会崩」变成「几秒 + 稳定」**，10–20 倍加速，落进可用区间。所需显存 4–6 GB，任何 ≥8 GB 的现代 NVIDIA 卡都够（推荐 **L4**，够省选 **T4**）。
2. **改动极小**：llama.cpp `server` → `server-cuda` 镜像 + `--gpus all -ngl 99 --ctx-size 8192 --parallel 3`。Phase 3–8、prompt、`ocr.py`、`/v1/ocr` 全不动。
3. **落地路线建议**：
   - **先**：在一台任意云 GPU（L4/T4 spot，~$0.5）上跑 `server-cuda` + 这两个 GGUF，做 `hunyuan_vl` mmproj 的 CUDA 兼容性 smoke test（唯一真实风险点），并重跑 Phase 9 的 50 张量一次真实 GPU latency。
   - **确认无误后**：生产按流量选 —— 突发/低量 → **Azure ACA serverless GPU（T4）**（最省，接受冷启动）；要恒定低延迟 → 常开 **T4 / 1/6 A10** VM 或 ACI。
4. **不建议**：任何 CPU-only 的 Azure 服务（会复现当前问题）、A100/H100（浪费）、Azure ML endpoint（过度封装）。

评估到此。是否实际部署、选哪条路线，等你决定。
