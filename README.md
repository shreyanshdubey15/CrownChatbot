# 👑 CrownChatbot: Dial Phone Elite Sales Intelligence

> **Carrier-Grade Telecom Sales AI — Tier-1 wholesale telecom sales strategist with RAG-powered document intelligence.**

CrownChatbot (Dial Phone) is a sophisticated AI platform designed for the telecom industry. It leverages Retrieval-Augmented Generation (RAG) to transform static company documents, compliance manuals, and rate sheets into an interactive, high-speed sales intelligence engine.

---

## ⚡ Key Capabilities

- **🧠 RAG-Powered Chat**: Natural language interface to query your entire document library. Get instant answers on routing, rates, compliance, and partner qualifications.
- **⚡ Smart Form Autofill**: Automatically extract data from unstructured documents to fill complex forms, templates, or compliance sheets.
- **🔍 Semantic Search**: Advanced vector-based search that understands context, not just keywords, across all your technical and legal documents.
- **🏢 Entity-Centric Intelligence**: Organized data extraction focused on companies, EINs, and carrier partners.
- **🛡️ Restricted Item Management**: automated extraction and categorization of prohibited or non-provided services (Illegal activities, Scam/Fraud patterns).
- **📖 Technical Dictionary**: AI-generated definitions for industry-specific terms (USF, KYC, Aggregator, etc.) sourced directly from your knowledge base.
- **📋 Template Library**: Save and manage form templates for rapid recurring workflows.
- **✅ Approval Workflow**: Human-in-the-loop review system for high-stakes AI-generated submissions.

---

## 🛠️ Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **Vector Database**: [Weaviate](https://weaviate.io/) (Local Instance)
- **AI/LLM Support**: 
  - **Cloud**: [Groq](https://groq.com/) (Llama 3 / Mixtral for extreme speed)
  - **Local**: [Ollama](https://ollama.com/) (Private offline processing)
- **Embeddings**: Sentence-Transformers (Local execution)
- **Processing**: [Unstructured.io](https://unstructured.io/) for document parsing (PDF, DOCX, XLSX, HEIF).
- **Frontend**: Modern Vanilla JS/CSS (Responsive Dashboard)

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Weaviate**: A local Weaviate instance running (default: `http://localhost:8080`).
- **Ollama** (Optional for local inference): [Download here](https://ollama.com/).
- **Groq API Key** (Optional for cloud inference): [Get Key](https://console.groq.com/).

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/shreyanshdubey15/CrownChatbot.git
   cd CrownChatbot/ChatBot
   ```

2. **Set up Virtual Environment**:
   ```bash
   # Windows
   python -m venv libbb
   .\libbb\Scripts\activate

   # Unix/macOS
   python3 -m venv libbb
   source libbb/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**:
   Create a `.env` file in the `ChatBot` directory (or use the provided template):
   ```env
   GROQ_API_KEY=your_key_here
   LLM_PROVIDER=ollama  # choices: ollama, groq
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_CHAT_MODEL=llama3:8b
   ```

### Running the App

```bash
python app.py
```
The server will start at `http://127.0.0.1:8000`. Access the dashboard at the root URL.

---

## 📁 Project Structure

```text
CrownChatbot/
├── ChatBot/
│   ├── api/            # FastAPI route handlers & models
│   ├── core/           # Core business logic
│   ├── ingestion/      # Document processing & vectorization
│   ├── rag_pipeline/   # RAG logic, embeddings, and chains
│   ├── memory/         # Chat history & session management
│   ├── frontend/       # Static assets (HTML/CSS/JS)
│   ├── data/           # Uploaded documents & temp storage
│   └── app.py          # Main entry point & lifespan orchestrator
└── README.md
```

---

## 🔌 API Overview

- `GET /health`: Check server and database status.
- `POST /rag/query`: Ask questions to the AI chain.
- `POST /ingest/upload`: Upload and index new documents.
- `POST /autofill/process`: Run the extraction engine on a document.
- `GET /documents`: List and manage current library.
- `GET /restricted-items`: Access the prohibited services database.

---

## 🔒 Security & Privacy

- **Local Processing**: When using Ollama and local Weaviate, your documents NEVER leave your infrastructure.
- **PII Handling**: Built-in logic to identify and handle sensitive entities like EINs and Company IDs.

---

Designed for **Dial Phone — Elite Sales Intelligence**.