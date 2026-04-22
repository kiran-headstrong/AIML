# ✈️ AeroManual AI

An intelligent document Q&A application powered by Retrieval-Augmented Generation (RAG). Upload training manuals, technical documents (PDF, DOCX, TXT, etc.), and ask questions — AeroManual AI retrieves relevant context and generates accurate answers using Groq's Llama 3.1 model.

---

## 📐 High-Level Architecture

```
 ┌──────────┐       ┌───────────────┐       ┌──────────────────┐
 │          │       │               │       │                  │
 │  👤 User │──────▶│  🖥️ Streamlit │──────▶│  ⚡ FastAPI       │
 │          │       │     UI        │       │   Backend        │
 └──────────┘       └───────────────┘       └────────┬─────────┘
                                                     │
                            ┌────────────────────────┼────────────────────────┐
                            │                        │                        │
                            ▼                        ▼                        ▼
                    ┌───────────────┐      ┌─────────────────┐     ┌──────────────────┐
                    │ 📄 Document   │      │ 🗂️ FAISS Vector │     │ 🤖 Groq LLM      │
                    │    Loader     │      │     Store       │     │  Llama 3.1 8B    │
                    │               │      │                 │     │                  │
                    │ PDF/DOCX/TXT  │─────▶│  Embeddings +   │────▶│  Context-Aware   │
                    │ → Chunks      │      │  Similarity     │     │  Answer Gen      │
                    └───────────────┘      └─────────────────┘     └──────────────────┘
```

---

## 🔄 How It Works — The Two Main Flows

### 📤 Flow 1: Document Upload & Indexing

```
  📎 Upload File                    💾 Save                      📖 Load & Parse
 ┌────────────┐              ┌────────────────┐              ┌────────────────────┐
 │            │              │                │              │                    │
 │  User      │    ──────▶   │  uploads/      │    ──────▶   │  Detect File Type  │
 │  selects   │   POST       │  directory     │              │  PDF → PyPDFLoader │
 │  file      │   /upload    │                │              │  DOCX → Docx2txt   │
 │            │              │                │              │  TXT → TextLoader  │
 └────────────┘              └────────────────┘              └─────────┬──────────┘
                                                                      │
                                                                      ▼
  ✅ Done!                     🗂️ Store                       ✂️ Split into Chunks
 ┌────────────┐              ┌────────────────┐              ┌────────────────────┐
 │            │              │                │              │                    │
 │  Response: │    ◀──────   │  FAISS Index   │    ◀──────   │  500 chars/chunk   │
 │  filename  │              │  saved to disk │              │  100 char overlap  │
 │  + count   │              │  vectorstore/  │              │                    │
 │            │              │                │              │  → Embed with      │
 └────────────┘              └────────────────┘              │  MiniLM-L6-v2      │
                                                             └────────────────────┘
```

### ❓ Flow 2: Question Answering

```
  💬 Ask Question                🔍 Embed & Search              📚 Get Context
 ┌────────────┐              ┌────────────────┐              ┌────────────────────┐
 │            │              │                │              │                    │
 │  User      │    ──────▶   │  Convert to    │    ──────▶   │  FAISS returns     │
 │  types     │   POST       │  384-dim       │   similarity │  Top 8 most        │
 │  question  │   /query     │  vector        │   search     │  relevant chunks   │
 │            │              │                │              │                    │
 └────────────┘              └────────────────┘              └─────────┬──────────┘
                                                                      │
                                                                      ▼
  💡 Display Answer              🤖 Generate                   📝 Build Prompt
 ┌────────────┐              ┌────────────────┐              ┌────────────────────┐
 │            │              │                │              │                    │
 │  Answer +  │    ◀──────   │  Groq LLM      │    ◀──────   │  Context:          │
 │  Source    │              │  Llama 3.1 8B  │              │  [8 chunks]        │
 │  files     │              │  temp = 0.3    │              │                    │
 │  shown     │              │                │              │  Question:         │
 └────────────┘              └────────────────┘              │  [user question]   │
                                                             └────────────────────┘
```

---

## 🧩 RAG Pipeline — Under the Hood

```mermaid
flowchart LR
    subgraph "📥 INGESTION"
        A["📄 Raw Document"] --> B{"🔎 File Type?"}
        B -->|.pdf| C["PyPDFLoader"]
        B -->|.docx| D["Docx2txtLoader"]
        B -->|.txt| E["TextLoader"]
        B -->|other| F["UnstructuredLoader"]
        C & D & E & F --> G["✂️ Splitter\n500 chars | 100 overlap"]
        G --> H["📦 Chunks"]
    end

    subgraph "🧠 EMBEDDING"
        H --> I["🔢 MiniLM-L6-v2\n384-dim vectors"]
        I --> J[("🗂️ FAISS Index")]
    end

    subgraph "💡 RETRIEVAL + GENERATION"
        K["❓ Question"] --> L["🔢 Embed Question"]
        L --> M["🔍 Top-8 Search"]
        J -.-> M
        M --> N["📝 Prompt\nContext + Question"]
        N --> O["🤖 Groq Llama 3.1"]
        O --> P["✅ Answer + Sources"]
    end

    style A fill:#e1f5fe
    style J fill:#fff3e0
    style O fill:#e8f5e9
    style P fill:#c8e6c9
```

---

## 🔀 Sequence Diagram — Full Interaction

```mermaid
sequenceDiagram
    actor User as 👤 User
    participant UI as 🖥️ Streamlit
    participant API as ⚡ AeroManual AI API
    participant DL as 📄 Doc Loader
    participant VS as 🗂️ FAISS
    participant LLM as 🤖 Groq LLM

    rect rgb(232, 245, 233)
        Note over User, LLM: 📤 Upload Flow
        User->>UI: Upload document
        UI->>API: POST /upload (file)
        API->>DL: Load & split file
        DL-->>API: Document chunks
        API->>VS: Embed & store chunks
        VS-->>API: ✅ chunks indexed
        API-->>UI: {filename, count}
        UI-->>User: ✅ Success!
    end

    rect rgb(227, 242, 253)
        Note over User, LLM: ❓ Query Flow
        User->>UI: Ask question
        UI->>API: POST /query {question}
        API->>VS: Similarity search (k=8)
        VS-->>API: Top 8 chunks
        API->>LLM: Context + Question
        LLM-->>API: Generated answer
        API-->>UI: {answer, sources}
        UI-->>User: 💡 Answer + Sources
    end
```

---

## 🏗️ Project Structure

```
Projects/AeroManual-AI/
│
├── 📂 app/
│   ├── __init__.py .............. Package init
│   ├── config.py ................ Settings & parameters
│   ├── document_loader.py ....... Load & split documents
│   ├── vector_store.py .......... FAISS index operations
│   ├── rag_chain.py ............. RAG chain (retrieval + LLM)
│   └── api.py ................... FastAPI endpoints + Prometheus metrics
│
├── 📂 k8s/
│   ├── namespace.yml ............ Kubernetes namespace
│   ├── secret.yml ............... GROQ_API_KEY secret
│   ├── pvc.yml .................. Persistent volume claims
│   ├── api-deployment.yml ....... API deployment & service
│   ├── ui-deployment.yml ........ UI deployment & service
│   └── monitoring.yml ........... Prometheus + Grafana stack
│
├── 📂 monitoring/
│   ├── prometheus.yml ........... Prometheus scrape config
│   └── grafana-datasource.yml ... Grafana datasource provisioning
│
├── 📂 uploads/ .................. Uploaded documents
├── 📂 vectorstore/ .............. Persisted FAISS index
│
├── Dockerfile ................... Container image (API + UI)
├── docker-compose.yml ........... Local multi-container setup
├── entrypoint.sh ................ Container entrypoint script
├── .dockerignore ................ Docker build exclusions
├── ui.py ........................ Streamlit chat UI
├── requirements.txt ............. Python dependencies
└── README.md .................... This file
```

---

## 🔧 Configuration

| Parameter | Value | Description |
|---|---|---|
| 🤖 `GROQ_MODEL` | `llama-3.1-8b-instant` | LLM for answer generation |
| 🧠 `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model (384-dim) |
| ✂️ `CHUNK_SIZE` | `500` | Characters per text chunk |
| 🔗 `CHUNK_OVERLAP` | `100` | Overlap between chunks |
| 🔍 `TOP_K` | `8` | Chunks retrieved per query |

---

## 🌐 API Endpoints

| Method | Endpoint | Input | Output |
|---|---|---|---|
| `POST` | `/upload` | File (multipart) | `{filename, chunks_indexed}` |
| `POST` | `/query` | `{question: string}` | `{answer, sources}` |
| `GET` | `/health` | — | `{status: "ok"}` |
| `GET` | `/metrics` | — | Prometheus metrics (auto-instrumented) |

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Groq API key (free at [console.groq.com](https://console.groq.com))

### 1. Install Dependencies
```bash
cd Projects/AeroManual-AI
pip install -r requirements.txt
```

### 2. Configure Environment
Ensure the `.env` file in the AIML root directory (two levels up) contains:
```env
GROQ_API_KEY=<your_groq_api_key>
```

### 3. Run the Application

**Terminal 1 — API server:**
```bash
cd Projects/AeroManual-AI
set NO_PROXY=localhost,127.0.0.1
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — Streamlit UI:**
```bash
cd Projects/AeroManual-AI
set NO_PROXY=localhost,127.0.0.1
streamlit run ui.py
```

> ⚠️ The `NO_PROXY` and `--host 127.0.0.1` flags are required on corporate networks to bypass proxy interception of localhost traffic.

### 4. Open the App
Navigate to **http://localhost:8501** in your browser.

---

## 🐳 Docker Deployment

### Deployment Architecture (Docker Compose)

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                     Docker Compose Network                       │
 │                                                                  │
 │  ┌──────────────┐       ┌──────────────┐                        │
 │  │  🖥️ UI        │──────▶│  ⚡ API       │──── /metrics ──┐      │
 │  │  Streamlit   │       │  FastAPI     │                │      │
 │  │  :8501       │       │  :8000       │                │      │
 │  └──────────────┘       └──────┬───────┘                │      │
 │                                │                        │      │
 │                         ┌──────┴───────┐                │      │
 │                         │  📦 Volumes   │                │      │
 │                         │  uploads/     │                │      │
 │                         │  vectorstore/ │                │      │
 │                         └──────────────┘                │      │
 │                                                         │      │
 │  ┌──────────────┐       ┌──────────────┐                │      │
 │  │  📊 Grafana   │◀──────│  📈 Prometheus│◀───────────────┘      │
 │  │  :3000       │       │  :9090       │                        │
 │  └──────────────┘       └──────────────┘                        │
 └──────────────────────────────────────────────────────────────────┘
```

### Container Image

A single `Dockerfile` builds one image that runs either the API or the UI, controlled by the `SERVICE` environment variable:

| `SERVICE` value | What starts | Port |
|---|---|---|
| `api` | FastAPI (uvicorn) | 8000 |
| `ui` | Streamlit | 8501 |

### Build & Run with Docker Compose

```bash
cd Projects/AeroManual-AI

# 1. Create .env file with your API key
echo GROQ_API_KEY=<your_groq_api_key> > .env

# 2. Build and start all services
docker-compose up --build
```

This starts 4 containers:

| Service | URL | Description |
|---|---|---|
| API | http://localhost:8000 | FastAPI backend + `/metrics` endpoint |
| UI | http://localhost:8501 | Streamlit chat interface |
| Prometheus | http://localhost:9090 | Metrics collection & querying |
| Grafana | http://localhost:3000 | Dashboards & visualization (admin/admin) |

### Useful Docker Commands

```bash
# Build image only
docker build -t aeromanual-ai:latest .

# Run API container standalone
docker run -e SERVICE=api -e GROQ_API_KEY=<your_key> -p 8000:8000 aeromanual-ai:latest

# Run UI container standalone
docker run -e SERVICE=ui -e API_URL=http://host.docker.internal:8000 -p 8501:8501 aeromanual-ai:latest

# Stop all compose services
docker-compose down

# Rebuild after code changes
docker-compose up --build -d
```

---

## ☸️ Kubernetes Deployment

### Kubernetes Architecture

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                  Kubernetes Cluster (namespace: aeromanual)             │
 │                                                                         │
 │  ┌─────────────────────┐         ┌─────────────────────────┐           │
 │  │  🖥️ UI Deployment    │         │  ⚡ API Deployment       │           │
 │  │  (1 replica)        │────────▶│  (2 replicas)           │           │
 │  │                     │         │                         │           │
 │  │  Service: LB :80    │         │  Service: ClusterIP     │           │
 │  │  → :8501            │         │  :8000                  │           │
 │  └─────────────────────┘         └────────────┬────────────┘           │
 │                                               │                        │
 │                                        ┌──────┴──────┐                 │
 │                                        │  📦 PVCs     │                 │
 │                                        │  uploads     │                 │
 │                                        │  vectorstore │                 │
 │                                        └─────────────┘                 │
 │                                               │                        │
 │                                          /metrics                      │
 │                                               │                        │
 │  ┌─────────────────────┐         ┌────────────┴────────────┐           │
 │  │  📊 Grafana          │◀────────│  📈 Prometheus           │           │
 │  │  Service: LB :3000  │         │  Service: ClusterIP     │           │
 │  │  (admin/admin)      │         │  :9090                  │           │
 │  └─────────────────────┘         └─────────────────────────┘           │
 │                                                                         │
 │  ┌─────────────────────┐                                               │
 │  │  🔐 Secret           │                                               │
 │  │  GROQ_API_KEY       │                                               │
 │  └─────────────────────┘                                               │
 └─────────────────────────────────────────────────────────────────────────┘
```

### Prerequisites

- Docker installed
- `kubectl` configured with access to a Kubernetes cluster
- A container registry (Docker Hub, Amazon ECR, etc.)

### Step 1: Build & Push the Container Image

```bash
cd Projects/AeroManual-AI

# Build
docker build -t aeromanual-ai:latest .

# Tag for your registry
docker tag aeromanual-ai:latest <your-registry>/aeromanual-ai:latest

# Push
docker push <your-registry>/aeromanual-ai:latest
```

> 💡 If using Amazon ECR:
> ```bash
> aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
> docker tag aeromanual-ai:latest <account-id>.dkr.ecr.<region>.amazonaws.com/aeromanual-ai:latest
> docker push <account-id>.dkr.ecr.<region>.amazonaws.com/aeromanual-ai:latest
> ```

### Step 2: Update Image References

Edit `k8s/api-deployment.yml` and `k8s/ui-deployment.yml` — replace `image: aeromanual-ai:latest` with your full registry path:

```yaml
image: <your-registry>/aeromanual-ai:latest
```

### Step 3: Configure the Secret

Edit `k8s/secret.yml` and replace the placeholder with your actual Groq API key:

```yaml
stringData:
  GROQ_API_KEY: "<your_actual_groq_api_key>"
```

### Step 4: Deploy to Kubernetes

```bash
# Create namespace
kubectl apply -f k8s/namespace.yml

# Create secret (contains GROQ_API_KEY)
kubectl apply -f k8s/secret.yml

# Create persistent volume claims for uploads & vectorstore
kubectl apply -f k8s/pvc.yml

# Deploy API (2 replicas with health probes)
kubectl apply -f k8s/api-deployment.yml

# Deploy UI (Streamlit frontend)
kubectl apply -f k8s/ui-deployment.yml

# Deploy monitoring stack (Prometheus + Grafana)
kubectl apply -f k8s/monitoring.yml
```

### Step 5: Verify Deployment

```bash
# Check all resources
kubectl get all -n aeromanual

# Check pod status
kubectl get pods -n aeromanual

# View API logs
kubectl logs -l app=aeromanual-api -n aeromanual

# View UI logs
kubectl logs -l app=aeromanual-ui -n aeromanual
```

### Step 6: Access the Application

```bash
# Get external IPs for LoadBalancer services
kubectl get svc -n aeromanual
```

| Service | Access |
|---|---|
| UI | `http://<UI-EXTERNAL-IP>` (port 80) |
| Grafana | `http://<GRAFANA-EXTERNAL-IP>:3000` (admin/admin) |
| API (internal) | `http://aeromanual-api:8000` (cluster-internal only) |
| Prometheus (internal) | `http://prometheus:9090` (cluster-internal only) |

### Kubernetes Manifest Summary

| File | Resources Created |
|---|---|
| `k8s/namespace.yml` | `aeromanual` namespace |
| `k8s/secret.yml` | Secret with `GROQ_API_KEY` |
| `k8s/pvc.yml` | 2 PVCs — `uploads-pvc` (2Gi), `vectorstore-pvc` (2Gi) |
| `k8s/api-deployment.yml` | Deployment (2 replicas, liveness/readiness probes) + ClusterIP Service |
| `k8s/ui-deployment.yml` | Deployment (1 replica) + LoadBalancer Service |
| `k8s/monitoring.yml` | Prometheus Deployment + ConfigMap + Grafana Deployment + ConfigMap + Services |

### API Pod Configuration

| Setting | Value |
|---|---|
| Replicas | 2 |
| CPU request / limit | 250m / 1 core |
| Memory request / limit | 512Mi / 2Gi |
| Liveness probe | `GET /health` every 30s |
| Readiness probe | `GET /health` every 10s |
| Prometheus annotations | Auto-scrape on `:8000/metrics` |

---

## 📊 Monitoring with Prometheus & Grafana

### How It Works

```
  ⚡ FastAPI API                    📈 Prometheus                  📊 Grafana
 ┌──────────────┐               ┌──────────────────┐          ┌──────────────────┐
 │              │   GET /metrics │                  │  PromQL  │                  │
 │  Handles     │◀──────────────│  Scrapes metrics │◀─────────│  Visualizes      │
 │  requests    │──────────────▶│  every 15s       │─────────▶│  dashboards      │
 │              │   JSON metrics│                  │  query   │                  │
 │  Exposes:    │               │  Stores time     │  results │  Pre-configured  │
 │  /metrics    │               │  series data     │          │  Prometheus      │
 │              │               │                  │          │  datasource      │
 └──────────────┘               └──────────────────┘          └──────────────────┘
```

The `prometheus-fastapi-instrumentator` library automatically instruments the FastAPI app and exposes metrics at the `/metrics` endpoint.

### Metrics Exposed

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Total HTTP requests by method, status, path |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_progress` | Gauge | Currently active requests |
| `http_request_size_bytes` | Summary | Request body sizes |
| `http_response_size_bytes` | Summary | Response body sizes |

### Grafana Dashboard Setup

1. Open Grafana at `http://localhost:3000` (Docker) or `http://<GRAFANA-EXTERNAL-IP>:3000` (K8s)
2. Login with `admin` / `admin`
3. Prometheus datasource is auto-provisioned — no manual setup needed
4. Create a new dashboard and add panels with these PromQL queries:

| Panel | PromQL Query |
|---|---|
| Request Rate | `rate(http_requests_total[5m])` |
| Response Latency (p95) | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` |
| Error Rate (5xx) | `rate(http_requests_total{status=~"5.."}[5m])` |
| Active Requests | `http_requests_in_progress` |
| Request Duration Avg | `rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])` |
| Upload Endpoint Latency | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{handler="/upload"}[5m]))` |
| Query Endpoint Latency | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{handler="/query"}[5m]))` |

### Verify Metrics Are Working

```bash
# Docker Compose — check metrics endpoint
curl http://localhost:8000/metrics

# Kubernetes — port-forward to check
kubectl port-forward svc/aeromanual-api 8000:8000 -n aeromanual
curl http://localhost:8000/metrics

# Check Prometheus targets
# Open http://localhost:9090/targets — should show aeromanual-api as UP
```

---

## 🧰 Tools & Technologies

### Application Stack

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                          AeroManual-AI Tech Stack                           │
 │                                                                             │
 │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
 │  │  Frontend    │  │  Backend    │  │  AI / RAG   │  │  DevOps &       │   │
 │  │             │  │             │  │             │  │  Monitoring     │   │
 │  │  Streamlit  │  │  FastAPI    │  │  LangChain  │  │  Docker         │   │
 │  │  Requests   │  │  Uvicorn    │  │  Groq LLM   │  │  Kubernetes     │   │
 │  │             │  │  Pydantic   │  │  FAISS      │  │  Prometheus     │   │
 │  │             │  │             │  │  HuggingFace│  │  Grafana        │   │
 │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘   │
 └─────────────────────────────────────────────────────────────────────────────┘
```

### Frontend

| Tool | Version | Purpose |
|---|---|---|
| [Streamlit](https://streamlit.io/) | latest | Interactive chat UI for document upload & Q&A |
| [Requests](https://docs.python-requests.org/) | latest | HTTP client for UI → API communication |

### Backend

| Tool | Version | Purpose |
|---|---|---|
| [FastAPI](https://fastapi.tiangolo.com/) | latest | High-performance async REST API framework |
| [Uvicorn](https://www.uvicorn.org/) | latest | ASGI server to run FastAPI |
| [Pydantic](https://docs.pydantic.dev/) | v2 | Request/response data validation |
| [python-multipart](https://github.com/Kludex/python-multipart) | latest | File upload handling in FastAPI |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | latest | Environment variable management from `.env` files |

### AI / RAG Pipeline

| Tool | Version | Purpose |
|---|---|---|
| [LangChain](https://python.langchain.com/) | latest | RAG orchestration framework (chains, prompts, output parsers) |
| [LangChain-Groq](https://python.langchain.com/docs/integrations/chat/groq/) | latest | Groq LLM integration for fast inference |
| [LangChain-HuggingFace](https://python.langchain.com/docs/integrations/text_embedding/huggingfacehub/) | latest | HuggingFace embedding model integration |
| [LangChain-Community](https://python.langchain.com/docs/integrations/) | latest | Document loaders (PDF, DOCX, TXT, Unstructured) |
| [Groq — Llama 3.1 8B](https://console.groq.com/) | `llama-3.1-8b-instant` | LLM for context-aware answer generation |
| [Sentence-Transformers](https://www.sbert.net/) | latest | Embedding model framework |
| [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | — | 384-dim embedding model for semantic search |
| [FAISS (CPU)](https://github.com/facebookresearch/faiss) | latest | Vector similarity search & indexing |

### Document Processing

| Tool | Purpose |
|---|---|
| [PyPDF](https://pypdf.readthedocs.io/) | PDF document loading & text extraction |
| [python-docx](https://python-docx.readthedocs.io/) | DOCX document loading |
| [Unstructured](https://unstructured.io/) | Fallback loader for other file formats |
| [LangChain Text Splitters](https://python.langchain.com/docs/how_to/recursive_text_splitter/) | Recursive character-based text chunking |

### Containerization & Orchestration

| Tool | Purpose |
|---|---|
| [Docker](https://www.docker.com/) | Containerize the application (single image for API + UI) |
| [Docker Compose](https://docs.docker.com/compose/) | Multi-container local deployment (API, UI, Prometheus, Grafana) |
| [Kubernetes](https://kubernetes.io/) | Production container orchestration with scaling, health probes, secrets |
| [kubectl](https://kubernetes.io/docs/reference/kubectl/) | Kubernetes CLI for deployment management |

### Monitoring & Observability

| Tool | Purpose |
|---|---|
| [Prometheus](https://prometheus.io/) | Metrics collection, storage & querying (scrapes `/metrics` every 15s) |
| [Grafana](https://grafana.com/) | Metrics visualization, dashboards & alerting |
| [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator) | Auto-instruments FastAPI with Prometheus metrics |

### Language & Runtime

| Tool | Version | Purpose |
|---|---|---|
| [Python](https://www.python.org/) | 3.10+ (3.11 in Docker) | Programming language |
| [pip](https://pip.pypa.io/) | latest | Python package manager |

---

## 📚 References & Resources

### RAG & LangChain

| Resource | Link |
|---|---|
| LangChain Documentation | https://python.langchain.com/docs/ |
| LangChain RAG Tutorial | https://python.langchain.com/docs/tutorials/rag/ |
| RAG Explained (AWS) | https://aws.amazon.com/what-is/retrieval-augmented-generation/ |
| FAISS Documentation | https://faiss.ai/ |
| Sentence-Transformers Docs | https://www.sbert.net/docs/ |
| all-MiniLM-L6-v2 Model Card | https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 |

### LLM & Groq

| Resource | Link |
|---|---|
| Groq Console (API Keys) | https://console.groq.com/ |
| Groq API Documentation | https://console.groq.com/docs/quickstart |
| Llama 3.1 Model Card | https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct |
| LangChain-Groq Integration | https://python.langchain.com/docs/integrations/chat/groq/ |

### FastAPI & Streamlit

| Resource | Link |
|---|---|
| FastAPI Documentation | https://fastapi.tiangolo.com/ |
| FastAPI Tutorial | https://fastapi.tiangolo.com/tutorial/ |
| Streamlit Documentation | https://docs.streamlit.io/ |
| Streamlit Chat Elements | https://docs.streamlit.io/develop/api-reference/chat |
| Uvicorn Documentation | https://www.uvicorn.org/ |

### Docker & Kubernetes

| Resource | Link |
|---|---|
| Docker Get Started | https://docs.docker.com/get-started/ |
| Dockerfile Reference | https://docs.docker.com/reference/dockerfile/ |
| Docker Compose Reference | https://docs.docker.com/compose/compose-file/ |
| Kubernetes Documentation | https://kubernetes.io/docs/home/ |
| Kubernetes Deployments | https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ |
| Kubernetes Services | https://kubernetes.io/docs/concepts/services-networking/service/ |
| Kubernetes Secrets | https://kubernetes.io/docs/concepts/configuration/secret/ |
| Kubernetes PersistentVolumeClaims | https://kubernetes.io/docs/concepts/storage/persistent-volumes/ |
| Amazon EKS (Managed K8s) | https://docs.aws.amazon.com/eks/latest/userguide/ |
| Amazon ECR (Container Registry) | https://docs.aws.amazon.com/ecr/latest/userguide/ |

### Monitoring & Observability

| Resource | Link |
|---|---|
| Prometheus Documentation | https://prometheus.io/docs/ |
| PromQL Basics | https://prometheus.io/docs/prometheus/latest/querying/basics/ |
| Grafana Documentation | https://grafana.com/docs/grafana/latest/ |
| Grafana Dashboard Tutorial | https://grafana.com/docs/grafana/latest/getting-started/build-first-dashboard/ |
| prometheus-fastapi-instrumentator | https://github.com/trallnag/prometheus-fastapi-instrumentator |
| Amazon CloudWatch (AWS Monitoring) | https://docs.aws.amazon.com/cloudwatch/latest/monitoring/ |
| Amazon Managed Grafana | https://docs.aws.amazon.com/grafana/latest/userguide/ |
| Amazon Managed Prometheus | https://docs.aws.amazon.com/prometheus/latest/userguide/ |

### Document Processing

| Resource | Link |
|---|---|
| PyPDF Documentation | https://pypdf.readthedocs.io/en/stable/ |
| python-docx Documentation | https://python-docx.readthedocs.io/en/latest/ |
| Unstructured Documentation | https://docs.unstructured.io/ |
| LangChain Document Loaders | https://python.langchain.com/docs/how_to/#document-loaders |
| LangChain Text Splitters | https://python.langchain.com/docs/how_to/recursive_text_splitter/ |

---

## 🛠️ Troubleshooting

### ❌ `ConnectionError: [WinError 10061] No connection could be made`

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                     🔍 Diagnosis Flowchart                             │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  Is the FastAPI server        │
                    │  actually running?            │
                    └──────────┬───────────┬────────┘
                               │           │
                          YES  │           │  NO
                               ▼           ▼
              ┌─────────────────┐   ┌──────────────────────────────┐
              │ Check for proxy  │   │ Run this to find the error:  │
              │ interference     │   │                              │
              │ (see below)      │   │ python -c                    │
              └─────────────────┘   │   "from app.api import app"  │
                                    └──────────────┬───────────────┘
                                                   │
                              ┌─────────────────────┼──────────────────────┐
                              │                     │                      │
                              ▼                     ▼                      ▼
                  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
                  │ ModuleNotFound:  │  │ ModuleNotFound:  │  │ Other import     │
                  │ langchain.       │  │ langchain.       │  │ error?           │
                  │ text_splitter    │  │ prompts          │  │                  │
                  │                  │  │                  │  │ pip install -r   │
                  │ ✅ Fix:          │  │ ✅ Fix:          │  │ requirements.txt │
                  │ Use import from  │  │ Use import from  │  │                  │
                  │ langchain_text_  │  │ langchain_core.  │  │                  │
                  │ splitters        │  │ prompts          │  │                  │
                  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

#### 🔧 Known Fixes (LangChain ≥ 1.x)

LangChain 1.x moved several modules. If you see import errors, apply these fixes:

| File | Old Import (broken) | Fixed Import |
|---|---|---|
| `app/document_loader.py` | `from langchain.text_splitter import ...` | `from langchain_text_splitters import RecursiveCharacterTextSplitter` |
| `app/rag_chain.py` | `from langchain.prompts import ...` | `from langchain_core.prompts import ChatPromptTemplate` |

#### 🌐 Corporate Proxy Blocking Localhost

If your machine uses a corporate proxy (e.g., McAfee Web Gateway), it may intercept `localhost` requests.

```
  ┌────────────┐         ┌──────────────┐         ┌────────────┐
  │ Streamlit  │──────▶  │ 🛡️ Corporate │──╳──▶   │  FastAPI   │
  │ UI :8501   │         │    Proxy     │  BLOCKED │  :8000     │
  └────────────┘         └──────────────┘         └────────────┘

  ✅ Fix: Bypass the proxy for local addresses

  ┌────────────┐                                  ┌────────────┐
  │ Streamlit  │──────────── DIRECT ─────────────▶│  FastAPI   │
  │ UI :8501   │   (NO_PROXY=localhost,127.0.0.1) │  :8000     │
  └────────────┘                                  └────────────┘
```

**Steps:**
1. Set `NO_PROXY` env var before starting both servers:
   ```bash
   set NO_PROXY=localhost,127.0.0.1
   ```
2. Bind uvicorn to `127.0.0.1` explicitly:
   ```bash
   uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
   ```
3. Ensure `ui.py` uses `http://127.0.0.1:8000` as the API URL (not `localhost`)

---

## 🚀 Quick Start Guide

Once the application is running (via any deployment method — see [Setup & Installation](#%EF%B8%8F-setup--installation), [Docker](#-docker-deployment), or [Kubernetes](#%EF%B8%8F-kubernetes-deployment) sections above), use it like this:

```
  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │             │     │             │     │             │     │             │     │             │
  │  1️⃣ Open    │────▶│  2️⃣ Upload  │────▶│  3️⃣ Process │────▶│  4️⃣ Ask     │────▶│  5️⃣ Get     │
  │  App        │     │  Docs       │     │  & Index    │     │  Questions  │     │  Answers!   │
  │  :8501      │     │  (sidebar)  │     │  (click)    │     │  (chat)     │     │  + Sources  │
  │             │     │             │     │             │     │             │     │             │
  └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

1. Open the Streamlit UI in your browser
2. Upload PDF, DOCX, or TXT documents using the sidebar
3. Click "Process & Index" to chunk and embed the documents
4. Ask questions in the chat input
5. Get AI-generated answers with source references

---

## ⚠️ Known Gaps & Limitations

### 🔴 Critical

| # | Gap | File | Description |
|---|---|---|---|
| 1 | **FAISS index reloaded from disk on every request** | `app/vector_store.py` | `_load_existing()` reads the full FAISS index from disk on every `search()` and `add_documents()` call. This is the single biggest performance bottleneck — every query pays disk I/O cost. |
| 2 | **Blocking sync operations in async endpoints** | `app/api.py` | Endpoints are declared `async` but call synchronous functions (`load_and_split`, `add_documents`, `ask`) directly. This blocks the event loop — one slow upload/query blocks all other concurrent requests. |
| 3 | **No file upload validation** | `app/api.py` | The `/upload` endpoint writes files to disk using the original filename with no sanitization. Risks include: **path traversal** (`../../etc/passwd`), **no file size limit** (a 10GB upload crashes the server), and **no content validation** (extension could be `.pdf` but contain malicious content). |

### 🟡 Important

| # | Gap | File | Description |
|---|---|---|---|
| 4 | **Race condition on FAISS index** | `app/vector_store.py` | Multiple concurrent uploads both call `add_documents()` which does load → add → save. Two simultaneous uploads can overwrite each other's changes — no file locking or concurrency control. |
| 5 | **No authentication** | `app/api.py` | The API has zero auth. Anyone with network access can upload documents and query the system. In a K8s deployment with a LoadBalancer, this is publicly exposed. |
| 6 | **No rate limiting** | `app/api.py` | No protection against abuse. A user could spam `/query` and exhaust the Groq API quota or overload the server. |
| 7 | **No structured logging** | All files | No logging anywhere. When something fails in production, there's no visibility beyond Prometheus request-level metrics. |
| 8 | **No CORS configuration** | `app/api.py` | FastAPI app has no CORS middleware. If the UI is ever served from a different domain/origin, API requests will be blocked by the browser. |
| 9 | **No dependency version pinning** | `requirements.txt` | All packages use `latest` with no version pins. A `pip install` today vs next month could install breaking changes (especially LangChain which changes frequently). |

### 🔵 Functional Gaps

| # | Gap | File | Description |
|---|---|---|---|
| 10 | **Hardcoded relevance threshold** | `app/vector_store.py` | The `score < 1.5` filter is a magic number. May filter out relevant results or let irrelevant ones through depending on document type and query. |
| 11 | **No duplicate document detection** | `app/vector_store.py` | Uploading the same file twice doubles the chunks in the index. No deduplication by filename or content hash. |
| 12 | **K8s PVC access mode mismatch** | `k8s/pvc.yml` | PVCs use `ReadWriteOnce` but the API deployment has 2 replicas. Only one pod can mount the volume — the second replica will fail to schedule. Should use `ReadWriteMany` or switch to a shared storage backend. |
| 13 | **No conversation memory** | `app/rag_chain.py` | Each query is independent. The LLM has no awareness of previous questions, so follow-up questions like "tell me more about that" won't work. |

---

## 🚀 Performance Improvement Roadmap

### Current Request Flow (Before Optimization)

```
  ❓ User Query
       │
       ▼
  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │                 │     │                 │     │                 │     │                 │
  │  📂 Load FAISS  │────▶│  🔍 Vector      │────▶│  🤖 Wait for    │────▶│  📤 Return      │
  │  from disk      │     │  Search         │     │  full LLM       │     │  full answer    │
  │  (SLOW)         │     │                 │     │  response       │     │                 │
  │                 │     │                 │     │  (SLOW)         │     │                 │
  └─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
        ~200ms                  ~50ms                  ~2-5s                    ~10ms
```

### Optimized Request Flow (After Improvements)

```
  ❓ User Query
       │
       ▼
  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │                 │     │                 │     │                 │     │                 │
  │  ⚡ In-memory   │────▶│  🔍 Vector      │────▶│  🤖 Stream LLM  │────▶│  📤 Stream      │
  │  FAISS lookup   │     │  Search +       │     │  tokens via     │     │  tokens to      │
  │  (FAST)         │     │  Reranker       │     │  SSE            │     │  user live      │
  │                 │     │  (BETTER)       │     │  (FAST UX)      │     │  (FAST UX)      │
  └─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
        ~1ms                   ~100ms                  ~2-5s                  immediate
                                                  (first token ~200ms)
```

### 🔴 High Impact Improvements

#### 1. Cache FAISS Index in Memory

**Problem**: `vector_store.py` calls `FAISS.load_local()` on every single request — reading the entire index from disk each time.

**Solution**: Load the index once into a module-level variable and only reload after new documents are added.

```python
# Before (current) — disk I/O on every request
def search(query, k=TOP_K):
    store = _load_existing()  # reads from disk every time
    results = store.similarity_search_with_score(query, k=k)
    ...

# After (optimized) — in-memory cache
_store_cache = None

def _get_store():
    global _store_cache
    if _store_cache is None:
        _store_cache = FAISS.load_local(_index_path, _embeddings, ...)
    return _store_cache

def add_documents(docs):
    global _store_cache
    store = _get_store() or FAISS.from_documents(docs, _embeddings)
    store.add_documents(docs)
    store.save_local(_index_path)
    _store_cache = store  # update cache
    return len(docs)
```

**Impact**: ~200ms → ~1ms per query (eliminates disk I/O).

#### 2. Run Sync Work in Thread Pool

**Problem**: `async` endpoints call blocking functions directly, freezing the event loop.

**Solution**: Use `asyncio.to_thread()` to offload CPU/IO-bound work.

```python
# Before (current) — blocks event loop
@app.post("/query")
async def query_documents(req: QueryRequest):
    return ask(req.question)  # blocks all other requests

# After (optimized) — runs in thread pool
import asyncio

@app.post("/query")
async def query_documents(req: QueryRequest):
    return await asyncio.to_thread(ask, req.question)
```

**Impact**: Concurrent requests no longer queue behind slow operations.

#### 3. Stream LLM Responses

**Problem**: Users wait 2-5 seconds staring at a spinner until the full LLM response is generated.

**Solution**: Use Groq's streaming API + Server-Sent Events (SSE) to show answers token-by-token.

```python
# API — stream tokens via SSE
from fastapi.responses import StreamingResponse

@app.post("/query/stream")
async def query_stream(req: QueryRequest):
    async def generate():
        docs = search(req.question)
        context = "\n\n---\n\n".join(d.page_content for d in docs)
        async for chunk in _chain.astream({"context": context, "question": req.question}):
            yield f"data: {chunk}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Impact**: First token appears in ~200ms instead of waiting 2-5s for the full response.

#### 4. Background Indexing for Uploads

**Problem**: Users wait for the entire chunking + embedding process during upload.

**Solution**: Return immediately after file save, index in background.

```python
from fastapi import BackgroundTasks

@app.post("/upload")
async def upload_document(file: UploadFile, background_tasks: BackgroundTasks):
    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    background_tasks.add_task(process_and_index, str(dest))
    return {"filename": file.filename, "status": "processing"}
```

**Impact**: Upload response time drops from seconds to milliseconds.

### 🟡 Medium Impact Improvements

#### 5. Add a Reranker After Retrieval

**Problem**: FAISS returns top-K by vector distance, but vector similarity doesn't always equal semantic relevance.

**Solution**: Add a cross-encoder reranker to reorder results by actual relevance before sending to the LLM.

```python
# pip install sentence-transformers
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def search_with_rerank(query, k=TOP_K):
    candidates = store.similarity_search(query, k=k * 2)  # fetch 2x candidates
    pairs = [(query, doc.page_content) for doc in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, score in ranked[:k]]
```

**Impact**: Significantly better answer quality — the LLM gets more relevant context.

#### 6. Increase Chunk Size

**Problem**: Current `CHUNK_SIZE=500` characters is quite small — chunks often cut mid-sentence, losing context.

**Solution**: Increase to 1000 chars with 200 overlap.

```python
# config.py
CHUNK_SIZE = 1000    # was 500
CHUNK_OVERLAP = 200  # was 100
```

**Impact**: Fewer chunks with more complete context → better LLM answers.

#### 7. Add Conversation Memory

**Problem**: Each query is independent — the LLM has no awareness of previous questions. Follow-up questions like "tell me more" or "what about section 3?" don't work.

**Solution**: Pass chat history in the prompt.

```python
_prompt = ChatPromptTemplate.from_template(
    """You are a helpful assistant. Use the context and chat history to answer.

Chat History:
{chat_history}

Context:
{context}

Question: {question}

Answer:"""
)
```

**Impact**: Enables natural multi-turn conversations.

#### 8. Batch Embedding During Upload

**Problem**: During document upload, chunks are embedded one-by-one by default.

**Solution**: LangChain's `FAISS.from_documents()` already batches internally, but for `add_documents()` on an existing store, ensure batch size is configured:

```python
_embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    encode_kwargs={"batch_size": 64}  # embed 64 chunks at once
)
```

**Impact**: 2-5x faster document indexing for large files.

### 🟢 Nice-to-Have Improvements

#### 9. Switch to FAISS GPU

Replace `faiss-cpu` with `faiss-gpu` in `requirements.txt` if a GPU is available. Vector search becomes ~10-100x faster for large indexes (100K+ chunks).

#### 10. Add Query Caching

Cache repeated queries with an LRU cache or Redis to avoid redundant Groq API calls:

```python
from functools import lru_cache

@lru_cache(maxsize=256)
def ask_cached(question: str) -> dict:
    return ask(question)
```

**Impact**: Instant responses for repeated questions, saves Groq API quota.

#### 11. Upgrade Embedding Model

Replace `all-MiniLM-L6-v2` (384-dim) with `all-mpnet-base-v2` (768-dim) for better retrieval accuracy at the cost of slightly more compute and memory:

```python
# config.py
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"  # was all-MiniLM-L6-v2
```

**Impact**: Better semantic matching → more relevant chunks → better answers.

### Improvement Priority Matrix

```
                        IMPACT
              Low            Medium           High
         ┌──────────────┬──────────────┬──────────────┐
  Easy   │              │  #6 Chunk    │  #1 FAISS    │
         │              │     Size     │     Cache    │
         │              │  #8 Batch    │  #2 Thread   │
         │              │     Embed    │     Pool     │
         ├──────────────┼──────────────┼──────────────┤
EFFORT   │  #9 FAISS    │  #7 Chat     │  #3 Stream   │
  Medium │     GPU      │     Memory   │     LLM      │
         │  #11 Embed   │  #5 Reranker │  #4 Bg Index │
         │     Model    │              │              │
         ├──────────────┼──────────────┼──────────────┤
  Hard   │              │  #10 Query   │              │
         │              │     Cache    │              │
         │              │              │              │
         └──────────────┴──────────────┴──────────────┘

  ✅ Start here: #1 → #2 → #3 (biggest bang for least effort)
```
