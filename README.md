# AI-Powered Forensic Sketch Generator & Chain of Custody System

---

### Institutional Information
- **Student Name:** Anubhav Kashyap
- **USN:** 1BY25CS051
- **Section:** CSE 2
- **Institution:** BMS Institute of Technology and Management (BMSIT)

---

## 📌 Project Overview
The **AI-Powered Forensic Sketch Generator** is a full-stack investigative tool designed for law enforcement agencies and forensic artists. It transforms natural language witness testimonies into precise, structured facial composite sketches, dynamically applies disguise and age modifiers, and records all modifications in an immutable, cryptographically verifiable **SHA-256 Chain of Custody Evidence Dossier**.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend Framework** | **FastAPI** (Python 3.11), **Uvicorn**, **Pydantic v2** |
| **Database & ORM** | **SQLite** (`nexus.db`), **SQLAlchemy** (async & sync engines) |
| **Frontend Framework** | **React 18**, **Vite**, **Tailwind CSS**, **Lucide Icons** |
| **AI / Generation Pipeline** | **Google Gemini** (structured trait extraction), **Pollinations.ai** (forensic line-art & composite sketches) |
| **Forensic Integrity** | **SHA-256** cryptographic hash chain, audit trail middleware, JSON evidence dossier export |
| **Automation & DevOps** | Root-level process orchestrator (`start_all.py` / `start_all.bat`), automated Git workflow |

---

## 🚀 Key Features

1. **Witness Description Parsing**:
   - Uses Google Gemini with strict JSON schema enforcement to parse unstructured witness narratives into structured facial traits (`jaw`, `hair`, `hair_color`, `face_width`, `disguises`, `notes`).

2. **Strict Forensic Prompt Builder & Deterministic Seeding**:
   - Generates standardized prompt templates:
     `"Forensic composite sketch portrait of a [age]-year-old individual, [hair description], featuring a [mustache description] and [beard description], [disguise toggles like sunglasses/glasses], highly detailed facial features, consistent mugshot style, black and white or sharp line art."`
   - Uses an MD5-derived deterministic seed (`% 1000000`) based on core facial traits to keep the base facial identity stable while allowing dynamic disguise additions (beards, mustaches, sunglasses, scars).

3. **Cryptographic SHA-256 Chain of Custody**:
   - Every modification, prompt alteration, and image generation step is logged to an immutable audit ledger.
   - Provides an `/api/export` endpoint that computes a SHA-256 hash across all case actions, ensuring tamper-evident evidence dossiers for court admissibility.

4. **One-Click Orchestration**:
   - Integrated `start_all.py` and `start_all.bat` launchers to spin up both FastAPI and Vite development servers concurrently with health verification.

---

## 📁 Repository Structure

```
├── ps01-sketch/
│   ├── backend/                      # FastAPI Backend
│   │   ├── app/
│   │   │   ├── api/routes/           # API Endpoints (auth, cases, sketch, audit, image)
│   │   │   ├── core/                 # Config & Security Middleware
│   │   │   ├── models.py             # SQLAlchemy Database Models
│   │   │   ├── schemas.py            # Pydantic v2 Schemas
│   │   │   └── services/             # Gemini, Image Pipeline, Audit Hashing
│   │   ├── main.py                   # FastAPI Application Entrypoint
│   │   └── requirements.txt          # Python Dependencies
│   └── ps01-sketch/                  # React + Vite Frontend
│       ├── src/
│       │   ├── components/           # UI Components (Canvas, Controls, AuditLog, Header)
│       │   └── App.jsx               # Application Root Component
│       ├── package.json              # Node Dependencies
│       └── vite.config.js            # Vite Configuration
├── start_all.py                      # Root Process Orchestrator (Python)
├── start_all.bat                     # Windows Batch Launcher
├── .gitignore                        # Git Ignore Rules
└── README.md                         # Project Documentation
```

---

## ⚡ Quick Start Guide

### 1. Automated Full-Stack Launch
To run both backend and frontend concurrently with automatic port binding:
```bash
python start_all.py
```
*Or double-click `start_all.bat` on Windows.*

### 2. Manual Startup

#### Backend Setup
```bash
cd ps01-sketch/backend
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
- API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Probe: [http://localhost:8000/healthz](http://localhost:8000/healthz)

#### Frontend Setup
```bash
cd ps01-sketch/ps01-sketch
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```
- Application UI: [http://localhost:5173](http://localhost:5173)

---

## 🔒 Security & Forensic Audit Trail

The system implements strict evidence integrity protocols:
- **Audit Middleware**: Automatically records timestamp, user ID, case ID, IP address, and payload parameters for every investigative action.
- **Dossier Export**: Produces a standardized JSON report containing suspect traits, rendered sketch data, full audit history, and a root SHA-256 verification digest:
  $$\text{Evidence Hash} = \text{SHA-256}(\text{CaseMetadata} \parallel \text{Traits} \parallel \text{AuditLogs})$$
