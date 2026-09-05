# ☸️ Kubernetes Setup Guide for AI-Service

This folder contains production-ready Kubernetes (k8s) manifests for deploying **`AI-Service`**, Qdrant Vector Database StatefulSet, and Horizontal Pod Autoscaler (HPA).

---

## 📁 Manifest Directory Overview

| Manifest File | Purpose & Resources Defined |
| :--- | :--- |
| **`namespace.yaml`** | Namespace `ai-service` for workload isolation. |
| **`configmap.yaml`** | Non-sensitive environment variables (`GEMINI_MODEL`, `QDRANT_HOST`, `PORT`, `LOG_LEVEL`). |
| **`secret.example.yaml`** | Secret template for database credentials, Google Gemini API key, OpenAI API key, and Qdrant secrets. |
| **`deployment.yaml`** | Deployment manifest for `ai-service` containers (Replicas: 3) with `/health` liveness & readiness probes. |
| **`service.yaml`** | `ClusterIP` Service exposing port `8002` internally. |
| **`qdrant-statefulset.yaml` & `qdrant-service.yaml`** | StatefulSet (10GB PVC) & Service for Qdrant Vector Database (Agent 6 memory). |
| **`hpa.yaml`** | Horizontal Pod Autoscaler scaling `AI-Service` pods from 2 to 10 based on CPU/RAM usage. |

---

## 🚀 Quick Deployment Guide

### Step 1: Create Secret File
Copy the example secret file and update sensitive API keys:
```bash
cp k8s/secret.example.yaml k8s/secret.yaml
```

### Step 2: Apply Manifests
Apply all manifests in the correct order:
```bash
# 1. Create Namespace
kubectl apply -f k8s/namespace.yaml

# 2. Apply ConfigMap & Secret
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# 3. Deploy Qdrant Vector Database StatefulSet
kubectl apply -f k8s/qdrant-statefulset.yaml
kubectl apply -f k8s/qdrant-service.yaml

# 4. Deploy AI Service Web Application & Autoscaler
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

### Step 3: Verify Deployment Health
```bash
# Check pod status in ai-service namespace
kubectl get pods -n ai-service

# Check services & HPA autoscaler
kubectl get svc -n ai-service
kubectl get hpa -n ai-service
```
