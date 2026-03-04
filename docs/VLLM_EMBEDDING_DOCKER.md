# 用 vLLM Docker 部署 Embedding 模型

vLLM 官方镜像支持挂载 **embedding 模型**，对外提供 OpenAI 兼容的 `/v1/embeddings`，供 meeting-agent 的 RAG 使用。

**与项目里 vLLM（LLM）的写法一致**：同镜像 `vllm/vllm-openai:latest`、同参数风格（`--model=...`），仅把模型换成 embedding 模型、端口与容器名区分即可。K8s 部署见 [K8S_DEPLOY.md](K8S_DEPLOY.md) 第 4 节。

---

## 1. 与 vLLM LLM（Chat）的对应关系

| 用途 | 镜像 | 端口示例 | 模型示例 | 接口 |
|------|------|----------|----------|------|
| **LLM（Chat）** | `vllm/vllm-openai:latest` | 8000 | `Qwen/Qwen2.5-7B-Instruct` | `/v1/chat/completions` |
| **Embedding**   | `vllm/vllm-openai:latest` | 8001 | `BAAI/bge-small-zh-v1.5`  | `/v1/embeddings` |

本地可同时跑两个容器：LLM 用 8000、Embedding 用 8001，写法参考下面并排命令。

**vLLM LLM（Chat，参考用）**：

```bash
docker run -d \
  --name vllm-llm \
  --gpus all \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct \
  --served-model-name default
```

**vLLM Embedding（本文重点）**：

```bash
docker run -d \
  --name vllm-embedding \
  --gpus all \
  -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model BAAI/bge-small-zh-v1.5
```

---

## 2. 前置条件

- 已安装 Docker（如需 GPU：安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)）。
- 有足够内存/显存：小模型（如 bge-small）约 1～2GB，大模型按官方说明。

---

## 3. 一键运行 Embedding（GPU）

```bash
docker run -d \
  --name vllm-embedding \
  --gpus all \
  -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model BAAI/bge-small-zh-v1.5
```

- **GPU**：上面使用 `--gpus all`；若报错 `unknown or invalid runtime name: nvidia`，见第 9 节故障排查（可先去掉 GPU 参数用 CPU 跑，或安装 NVIDIA Container Toolkit）。
- **端口**：容器内 8000，映射到主机 `8001`（避免与本地已有 vLLM chat 的 8000 冲突）。
- **模型**：`BAAI/bge-small-zh-v1.5` 为中文小模型，适合 RAG；可换成 `BAAI/bge-m3`、`BAAI/bge-large-zh-v1.5` 等（显存需更大）。
- **模型是否要先下载**：不用。首次启动时若机器能访问外网，vLLM 会**自动从 Hugging Face 下载**该模型；下载完成后服务才就绪。若需离线或提前拉取，可在宿主机先下载到 `~/.cache/huggingface`，再通过上面的 `-v` 挂载进容器复用。
- **缓存**：`-v ~/.cache/huggingface:...` 把 Hugging Face 缓存挂进容器，首次下载后下次启动直接用本地缓存，无需重复拉取。

---

## 3.1 从 ModelScope（魔搭）下载

若希望从 **ModelScope 魔搭** 拉取模型（国内网络更友好），在启动容器时加上环境变量 `VLLM_USE_MODELSCOPE=True`，并挂载魔搭缓存目录（可选，用于持久化）：

```bash
docker run -d \
  --name vllm-embedding \
  --gpus all \
  -p 8001:8000 \
  -e VLLM_USE_MODELSCOPE=True \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/.cache/modelscope:/root/.cache/modelscope \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model BAAI/bge-small-zh-v1.5
```

- 设置 `VLLM_USE_MODELSCOPE=True` 后，vLLM 会从 [modelscope.cn](https://www.modelscope.cn) 解析并下载模型，模型 ID 一般与 Hugging Face 一致（如 `BAAI/bge-small-zh-v1.5`）。
- 挂载 `~/.cache/modelscope` 便于首次下载后下次启动直接用本地缓存。

**宿主机预下载（可选）**：在内网或想提前拉好时，可在本机用 ModelScope SDK 先下载（默认会存到 `~/.cache/modelscope`），再挂载该目录给容器：

```bash
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5')"
# 然后 docker run 时加上 -v ~/.cache/modelscope:/root/.cache/modelscope
```

若魔搭上该模型不在 `BAAI/` 下，到 [ModelScope 官网](https://www.modelscope.cn) 搜「bge-small-zh」查看实际仓库名，把 `--model` 换成对应 ID。

**ModelScope 本地路径**：魔搭下载后，模型在容器内路径为 `/root/.cache/modelscope/hub/models/<组织>/<模型名>`。例如 Qwen3-Embedding-8B 为：

- 容器内：`/root/.cache/modelscope/hub/models/Qwen/Qwen3-Embedding-8B`
- 宿主机（挂载 `~/.cache/modelscope` 时）：`~/.cache/modelscope/hub/models/Qwen/Qwen3-Embedding-8B`

若已预下载并挂载了 `-v ~/.cache/modelscope:/root/.cache/modelscope`，可直接用本地路径启动，无需再设 `VLLM_USE_MODELSCOPE`、也无需联网：

```bash
--model /root/.cache/modelscope/hub/models/Qwen/Qwen3-Embedding-8B
```

---

## 4. 无 GPU 时能否用 CPU 跑？

**不能。** 官方镜像 `vllm/vllm-openai` 是按 **CUDA** 构建的，依赖 `libcuda.so.1`。在未挂载 GPU（或未配置 nvidia 运行时）的机器上，去掉 `--gpus all` 仍会报错：

- `libcuda.so.1: cannot open shared object file`
- `Failed to infer device type`

即：**当前镜像不支持纯 CPU 运行**。可选做法：

| 做法 | 说明 |
|------|------|
| **本机有 GPU** | 安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)，配置好后用 `--gpus all` 启动（见第 9 节）。 |
| **本机无 GPU** | 不在本机起 vLLM Embedding。改用：① 有 GPU 的机器/云上起 vLLM，本机 `.env` 里 `EMBEDDING_BASE_URL` 指过去；② 或 `EMBEDDING_TYPE=openai` + `OPENAI_API_KEY` 用云端 Embedding。 |

若必须在本机无 GPU 环境下跑 embedding，需自建 CPU 版 vLLM 镜像（构建时设 `VLLM_TARGET_DEVICE=cpu`），或使用其他提供 `/v1/embeddings` 的 CPU 友好方案（如自建 sentence-transformers 服务）。

---

## 5. 验证服务

```bash
curl -X POST http://localhost:8001/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"BAAI/bge-small-zh-v1.5","input":"测试文本"}'
```

返回 JSON 且含 `data[0].embedding` 即表示正常。

---

## 6. meeting-agent 配置

在 `.env` 中指向该 Embedding 服务（端口与上面一致）：

```bash
EMBEDDING_TYPE=api
EMBEDDING_BASE_URL=http://localhost:8001/v1
# 若模型名与上面 --model 一致，可不填；否则用 EMBEDDING_MODEL 指定请求时的 model 参数
# EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

若 Embedding 服务在其它机器，把 `localhost` 改为该机 IP 或域名。

---

## 7. Docker Compose 示例（可选）

与 LLM 分开、便于一起管理：

```yaml
# docker-compose.embedding.yml
services:
  vllm-embedding:
    image: vllm/vllm-openai:latest
    container_name: vllm-embedding
    ports:
      - "8001:8000"
    volumes:
      - huggingface_cache:/root/.cache/huggingface
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    ipc: host
    command: ["--model", "BAAI/bge-small-zh-v1.5"]

volumes:
  huggingface_cache:
```

运行：`docker compose -f docker-compose.embedding.yml up -d`。  
无 GPU 时去掉 `deploy.resources.reservations`，并确保已按 vLLM 文档启用 CPU 模式（若支持）。

---

## 8. 常用 Embedding 模型

| 模型 | 说明 | 显存大致需求 |
|------|------|----------------|
| `BAAI/bge-small-zh-v1.5` | 中文小模型，推荐起步 | ~1GB |
| `BAAI/bge-base-zh-v1.5` | 中文 base | ~2GB |
| `BAAI/bge-large-zh-v1.5` | 中文大模型 | ~4GB+ |
| `BAAI/bge-m3` | 多语言、支持长文本 | 更大 |
| **`Qwen/Qwen3-Embedding-0.6B`** | 0.6B、轻量、多语言；vLLM 需加 `--task embed`；**适合与 LLM 同卡** | ~1–2GB |
| **`Qwen/Qwen3-Embedding-8B`** | 8B 参数、多语言、32K 上下文、MTEB 领先；vLLM 需加 `--task embed` | ~18GB+ |

更多见 [vLLM 文档 - Pooling/Embedding 模型](https://docs.vllm.ai/en/latest/models/pooling_models/)。

### Qwen3-Embedding-0.6B（与 LLM 同卡推荐）

显存约 1–2GB，可与 7B 级 LLM 共用一张 24GB 卡。同样需要 `--task embed`：

```bash
docker run -d \
  --name vllm-embedding \
  --gpus all \
  -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/.cache/modelscope:/root/.cache/modelscope \
  --ipc=host \
  vllm/vllm-openai:v0.10.2 \
  --model Qwen/Qwen3-Embedding-0.6B \
  --task embed
```

从魔搭拉取时加 `-e VLLM_USE_MODELSCOPE=True`；已下载到本地则可用路径 `--model /root/.cache/modelscope/hub/models/Qwen/Qwen3-Embedding-0.6B`。请求时 `model` 填 `Qwen/Qwen3-Embedding-0.6B`（或服务端 `--served-model-name`）。

### Qwen3-Embedding-8B 示例

该模型在 vLLM 中需显式指定 **`--task embed`**，否则会按生成模型加载。Docker 示例：

```bash
docker run -d \
  --name vllm-embedding \
  --gpus all \
  -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3-Embedding-8B \
  --task embed
```

从 ModelScope 拉取时加上 `-e VLLM_USE_MODELSCOPE=True` 和 `-v ~/.cache/modelscope:/root/.cache/modelscope`。

**已从魔搭下载到本地时**：模型在容器内路径为 `/root/.cache/modelscope/hub/models/Qwen/Qwen3-Embedding-8B`，可直接用该路径、无需联网。示例（固定镜像版本 v0.10.2；有 GPU 时在 `-p` 前加 `--gpus all`）：

```bash
docker run -d \
  --name vllm-embedding \
  -p 8001:8000 \
  -v ~/.cache/modelscope:/root/.cache/modelscope \
  --ipc=host \
  vllm/vllm-openai:v0.10.2 \
  --model /root/.cache/modelscope/hub/models/Qwen/Qwen3-Embedding-8B \
  --task embed
```

请求时 `model` 填 `Qwen/Qwen3-Embedding-8B`（或你在服务端配置的 `--served-model-name`）。

---

## 9. 故障排查

- **`Engine core initialization failed. See root cause above`**：引擎子进程启动失败，**根因在日志更上面**（如 OOM、CUDA 错误）。先看 `docker logs vllm-embedding 2>&1` 里该行之前的报错。可尝试关闭 V1 引擎：启动时加 `-e VLLM_USE_V1=0`（例如 `docker run ... -e VLLM_USE_V1=0 ...`），用旧引擎规避部分兼容问题。
- **`unknown or invalid runtime name: nvidia`**：当前 Docker 未配置 NVIDIA 运行时。在宿主机安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)，执行 `sudo nvidia-ctk runtime configure --runtime=docker`，重启 Docker，再用 `--gpus all` 启动。
- **`libcuda.so.1: cannot open shared object file` / `Failed to infer device type`**：说明容器内没有 GPU 或未挂载 NVIDIA 驱动。官方 vLLM 镜像是 CUDA 版，**不支持无 GPU 的纯 CPU 运行**。解决：在有 GPU 的机器上起容器并加上 `--gpus all`，或本机改用远程 Embedding 服务 / `EMBEDDING_TYPE=openai`（见第 4 节）。
- **502 / 连接被拒**：确认容器在跑（`docker ps`）、端口已映射，且 `EMBEDDING_BASE_URL` 的 host 和端口正确（含 `/v1`）。
- **OOM / CUDA out of memory**：换更小模型或增大显存。
- **模型下载慢**：挂载 `~/.cache/huggingface` 后首次拉取，之后复用；可设 `HUGGING_FACE_HUB_TOKEN` 用私有模型。

部署完成后，用 meeting-agent 的 book 接口或 `--check-vector-store` 仅能验证向量库；Embedding 是否正常需实际发起一次预定或自调 `/v1/embeddings` 如上。
