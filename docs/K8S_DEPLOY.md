# Kubernetes 自建服务部署指南

在 K8s 上自建 vLLM（LLM）、Embedding 服务、RAG 向量库，并与会议预定 Agent 对接。

---

## 1. 整体架构

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                     Kubernetes 集群                       │
  Ingress/网关       │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
  ───────────────►  │  │ meeting-    │  │ vllm-llm    │  │ vllm-embedding  │  │
                    │  │ agent       │──│ (chat)      │  │ (/v1/embeddings)│  │
                    │  │             │  └─────────────┘  └────────┬────────┘  │
                    │  │             │  ┌─────────────┐          │           │
                    │  │             │──│ qdrant       │◄─────────┘           │
                    │  └─────────────┘  │ (向量库)      │  (或 Weaviate)      │
                    │                  └─────────────┘                      │
                    └─────────────────────────────────────────────────────────┘
```

- **meeting-agent**：本应用，通过环境变量连上述服务。
- **vLLM（LLM）**：提供 `/v1/chat/completions`，供解析意图、回复润色。
- **Embedding 服务**：提供 `/v1/embeddings`，供 RAG 向量化；可与 vLLM 同栈（再起一个 vLLM 挂 embedding 模型）或单独实现。
- **向量库**：Qdrant / Weaviate，存 RAG 向量；或用 Chroma 内嵌于 meeting-agent（无需单独部署）。

---

## 2. 前置条件

- 已有 Kubernetes 集群（1.24+）。
- 若跑 vLLM 需要 **GPU 节点**：安装 [NVIDIA Device Plugin](https://github.com/NVIDIA/k8s-device-plugin)，节点带 CUDA 驱动。
- `kubectl`、`helm` 已安装并能访问集群。
- 若从私有镜像仓库拉镜像，需配置 imagePullSecrets。

---

## 3. 部署 vLLM（LLM 服务）

vLLM 提供 OpenAI 兼容的 `/v1/chat/completions`，本应用用其做意图解析与回复润色。

### 3.1 官方 Helm（推荐）

vLLM 提供 Helm Chart，支持 GPU、自动拉模型等。

```bash
# 添加 vLLM Helm 仓库（以官方文档为准，可能为 vllm 或 production-stack）
helm repo add vllm https://vllm-project.github.io/vllm-helm  # 或见 https://docs.vllm.ai/deployment/frameworks/helm.html
helm repo update

# 创建 namespace
kubectl create namespace ai-serving

# 自定义 values（GPU、模型名、资源等）
cat <<EOF > vllm-llm-values.yaml
# 示例：7B 模型，单卡
model:
  name: "Qwen/Qwen2.5-7B-Instruct"   # 或你的模型
gpu:
  count: 1
  type: "nvidia.com/gpu"
resources:
  limits:
    nvidia.com/gpu: 1
  requests:
    memory: "16Gi"
    cpu: "4"
service:
  type: ClusterIP
  port: 8000
EOF

helm upgrade --install vllm-llm vllm/vllm -n ai-serving -f vllm-llm-values.yaml
```

部署完成后，集群内访问地址一般为：`http://vllm-llm-xxx.ai-serving.svc.cluster.local:8000/v1`（以 Helm 实际 Release/Service 名为准）。

### 3.2 裸 Deployment 示例（无 Helm 时）

若不用 Helm，可用下面 YAML 做最小部署（需按实际镜像、模型、存储调整）：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-llm
  namespace: ai-serving
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-llm
  template:
    metadata:
      labels:
        app: vllm-llm
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - "--model=Qwen/Qwen2.5-7B-Instruct"
            - "--served-model-name=default"
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: "1"
            requests:
              memory: "16Gi"
              cpu: "2"
          env:
            - name: NVIDIA_VISIBLE_DEVICES
              value: "all"
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-llm
  namespace: ai-serving
spec:
  selector:
    app: vllm-llm
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
```

集群内访问：`http://vllm-llm.ai-serving.svc.cluster.local:8000/v1`。

---

## 4. 部署 Embedding 服务

本应用通过 `EMBEDDING_BASE_URL` 调用 **OpenAI 兼容的 `/v1/embeddings`**。可选两种方式。

### 4.1 方式一：再用 vLLM 挂 Embedding 模型（推荐）

很多 vLLM 版本支持 embedding 接口，可单独起一个 vLLM Deployment，只挂 embedding 模型（如 `BAAI/bge-small-zh-v1.5` 或 `BAAI/bge-m3`），与 LLM 分开扩缩容。**本地 Docker 写法**（与上面 vLLM LLM 同镜像、同风格）见 [DEPLOYMENT.md](DEPLOYMENT.md#5-用-vllm-docker-部署-embedding-模型) 第 5 节。

- **Helm**：同上，再 `helm install vllm-embedding ...`，换一个 model 名和 Service 名。
- **Deployment 示例**：与上面 vLLM LLM（3.2 节）类似，改 `--model` 为 embedding 模型、改 Service 名为 `vllm-embedding`。

集群内地址示例：`http://vllm-embedding.ai-serving.svc.cluster.local:8000/v1`。

### 4.2 方式二：独立 Embedding 服务（如 sentence-transformers + FastAPI）

若不用 vLLM 做 embedding，可自建一个提供 `/v1/embeddings` 的小服务（例如用 FastAPI + sentence-transformers），打成镜像在 K8s 里部署为 Deployment + Service，保证路径为 `/v1/embeddings`、请求/响应格式与 OpenAI 一致。本应用只需 `EMBEDDING_BASE_URL` 指向该 Service 的 `/v1` 即可。

---

## 5. 部署 RAG 向量库（Qdrant / Weaviate）

若不用内嵌 Chroma，可在 K8s 里部署 Qdrant 或 Weaviate，供 RAG 检索用。

### 5.1 Qdrant（Helm）

```bash
helm repo add qdrant https://qdrant.github.io/qdrant-helm
helm repo update

kubectl create namespace vector-db

helm upgrade --install qdrant qdrant/qdrant -n vector-db \
  --set persistence.enabled=true \
  --set persistence.size=10Gi
```

集群内访问：`http://qdrant.vector-db.svc.cluster.local:6333`（REST 默认 6333）。

### 5.2 Weaviate（Helm）

Weaviate 有官方/社区 Helm，可查 [Weaviate 文档](https://weaviate.io/developers/weaviate/installation/kubernetes)。部署后一般为 8080 端口，集群内例如：`http://weaviate.vector-db.svc.cluster.local:8080`。

### 5.3 不部署：用 Chroma 内嵌

本应用默认 `VECTOR_STORE_TYPE=chroma`，数据写在 meeting-agent 的持久化目录（需挂 PVC）。无需在 K8s 里单独起向量库服务。

---

## 6. 部署 meeting-agent（本应用）

在 K8s 里跑会议预定 Agent，通过环境变量指向上面各服务。

### 6.1 ConfigMap / Secret 示例

把非敏感配置放 ConfigMap，敏感放 Secret：

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: meeting-agent-config
  namespace: default
data:
  LLM_TYPE: "vllm"
  VLLM_BASE_URL: "http://vllm-llm.ai-serving.svc.cluster.local:8000/v1"
  EMBEDDING_TYPE: "api"
  EMBEDDING_BASE_URL: "http://vllm-embedding.ai-serving.svc.cluster.local:8000/v1"
  VECTOR_STORE_TYPE: "qdrant"
  QDRANT_URL: "http://qdrant.vector-db.svc.cluster.local:6333"
  # 若用 Chroma 内嵌，可改为：
  # VECTOR_STORE_TYPE: "chroma"
  # CHROMA_PERSIST_DIR: "/data/chroma_db"
  LOG_LEVEL: "INFO"
```

若用 Chroma，需在 Deployment 里把 `CHROMA_PERSIST_DIR` 对应目录挂到 PVC。

### 6.2 Deployment + Service 示例

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: meeting-agent
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: meeting-agent
  template:
    metadata:
      labels:
        app: meeting-agent
    spec:
      containers:
        - name: app
          image: your-registry/meeting-agent:latest
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: meeting-agent-config
            # - secretRef:
            #     name: meeting-agent-secret   # 可选：API Key 等
          volumeMounts:
            - name: data
              mountPath: /data
          resources:
            requests:
              memory: "512Mi"
              cpu: "200m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: meeting-agent-data   # 存 Chroma 等，若用 Qdrant 可不用
---
apiVersion: v1
kind: Service
metadata:
  name: meeting-agent
  namespace: default
spec:
  selector:
    app: meeting-agent
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
```

若用 Chroma，需先建 PVC：`meeting-agent-data`，并保证 `CHROMA_PERSIST_DIR=/data/chroma_db` 等与 `mountPath` 一致。

---

## 7. 服务发现与 URL 汇总

在 K8s 内，同一集群的服务通过 **Service 名.命名空间.svc.cluster.local:端口** 访问。示例（按你实际 namespace/Service 名改）：

| 组件 | 集群内 URL（示例） | 本应用环境变量 |
|------|--------------------|----------------|
| vLLM（LLM） | `http://vllm-llm.ai-serving.svc.cluster.local:8000/v1` | `VLLM_BASE_URL` |
| vLLM（Embedding） | `http://vllm-embedding.ai-serving.svc.cluster.local:8000/v1` | `EMBEDDING_BASE_URL` |
| Qdrant | `http://qdrant.vector-db.svc.cluster.local:6333` | `QDRANT_URL` |
| Weaviate | `http://weaviate.vector-db.svc.cluster.local:8080` | `WEAVIATE_URL` |

生产若通过 Ingress/网关对外暴露，只需在网关配置路由到 `meeting-agent` Service；本应用仍用上述**集群内 URL** 访问 vLLM、Embedding、向量库，无需改环境变量。

---

## 8. 建议顺序与校验

1. **先起向量库**（若用 Qdrant/Weaviate）：`helm install qdrant ...`，确认 Pod 正常、6333/8080 可连。
2. **再起 vLLM（LLM）**：确认 `/v1/chat/completions` 可调。
3. **再起 Embedding**：确认 `/v1/embeddings` 可调（用 curl 或本应用里 `EMBEDDING_BASE_URL` 指向该服务）。
4. **最后起 meeting-agent**：环境变量指向上面的 Service URL，健康检查 `GET /api/v1/health` 中 `checks.agent` 为 `ok` 即表示连上 LLM/Embedding 并完成初始化。
5. **配置校验**：启动前可用 `validate_settings()` 或 CLI（若实现 `--check-config`）检查必填项，避免缺配。

按上述顺序在 K8s 里自建 vLLM、Embedding 与（可选）RAG 向量库，再部署本应用即可。若你提供当前集群的 namespace、是否用 Helm、是否 GPU 等信息，可以再写一版贴合你环境的 values 或清单片段。
