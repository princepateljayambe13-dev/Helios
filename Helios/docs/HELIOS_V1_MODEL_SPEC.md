# HELIOS V1 MODEL REGISTRY SPECIFICATION

## System Specification: Computer Vision Models, Biometrics & Generative AI Model Registry

**Project:** HELIOS  
**Document:** Model Architecture, Weights, Input/Output Tensor Contracts & Execution Specs  
**Version:** 1.0 (Present Operational Architecture)  
**Status:** Active Production Specification  

---

# 1. Model Registry Overview

HELIOS employs a heterogeneous suite of specialized perception, biometric, and generative reasoning models:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          HELIOS MODEL REGISTRY                          │
├───────────────────────┬───────────────────────────┬─────────────────────┤
│ Model Name            │ Task / Function           │ Inference Runtime   │
├───────────────────────┼───────────────────────────┼─────────────────────┤
│ YOLO26s               │ Real-Time Object Detect   │ PyTorch / TensorRT  │
│ MobileFaceNet ArcFace │ Biometric Embeddings (512)│ PyTorch CPU / CUDA  │
│ Roboflow UAV Detector │ Drone Aerial Incursion    │ Roboflow Hosted/Edge│
│ CLIP (openai/clip-vit)│ Zero-Shot Vehicle Class   │ Hugging Face Hub    │
│ Gemini 1.5 Flash / Pro│ Strategic AI & VLM Inspect│ Google Cloud API    │
│ OpenRouter Reasoning  │ Gemma 31B & Nemotron 3.5  │ OpenRouter API      │
│ Ollama Qwen3:4b       │ Offline Local Reasoning   │ Local Ollama Daemon │
└───────────────────────┴───────────────────────────┴─────────────────────┘
```

---

# 2. Perception & Biometric Models

### 2.1 YOLO26s Object Detector (`models/detection/yolo26s.pt`)
- **Architecture**: Single-stage anchor-free convolutional detector optimized for edge GPUs.
- **Input Contract**: $640 \times 640 \times 3$ RGB normalized float32 tensor ($0.0 - 1.0$).
- **Output Contract**: Bounding boxes $[x_{\min}, y_{\min}, x_{\max}, y_{\max}]$, confidence score ($0.0 - 1.0$), and class index.
- **Monitored Classes**: Class 0 (`person`), Class 2 (`car`), Class 3 (`motorcycle`), Class 5 (`bus`), Class 7 (`truck`).
- **Latency**: $\approx 18\text{ms}$ on modern GPU, $\approx 85\text{ms}$ on multi-core CPU.

### 2.2 MobileFaceNet ArcFace (`app/vision/face/arcface.py`)
- **Architecture**: Depthwise-separable convolutional backbone with ArcFace angular margin loss.
- **Parameter Count**: ~3.4 million parameters.
- **Input Contract**: $112 \times 112 \times 3$ RGB normalized image.
- **Output Contract**: 512-dimensional floating-point vector with unit $L_2$ norm ($\|\mathbf{v}\|_2 = 1.0$).
- **Matching Operation**: Inner dot product ($\text{sim} = \mathbf{u} \cdot \mathbf{v}$). Match confirmed when $\text{sim} \ge 0.42$.

### 2.3 Vehicle Intelligence: Zero-Shot CLIP & HSV (`app/vision/vehicle_intelligence.py`)
- **Model**: `openai/clip-vit-base-patch32`.
- **Classification Categories**: SUV, pickup truck, hatchback, taxi, sedan, heavy truck, van, minivan, bus, motorcycle, bicycle, emergency vehicle, delivery truck.
- **Color Extractor**: Dual HSV saturation/hue thresholding combined with CLIP zero-shot color ranking across 12 standard automotive colors.

### 2.4 Roboflow UAV / Drone Detector (`app/vision/roboflow_uav.py`)
- **Model Endpoint**: `roboflow/drone-detection-aerial/1`.
- **Detection Classes**: `uav`, `quadcopter`, `fixed-wing`.
- **Input Contract**: Full HD frame ($1920 \times 1080$) or dynamic ROI tile.

---

# 3. Generative AI & Vision-Language Models

### 3.1 Google Gemini 1.5 Flash & Pro (`app/ai/client.py`)
- **Function**: Multi-turn operator assistance, structured threat daily briefs, and native high-resolution evidence analysis.
- **Context Window**: 1,000,000 tokens.
- **Tool Calling**: Native OpenAI-compatible JSON function definitions.

### 3.2 OpenRouter Reasoning Models (`google/gemma-4-31b-it:free`, `nemotron-3.5`)
- **Function**: Complex forensic reasoning and evidence correlation with internal thinking token preservation.
- **Reasoning Handling**: Automatically captures reasoning details from `<think>...</think>` output tags for security auditing.

### 3.3 Offline Local LLM: Ollama `qwen3:4b` (`app/ai/client.py`)
- **Function**: 100% offline, local edge execution without internet access.
- **Runtime**: Local HTTP daemon listening on `127.0.0.1:11434`.
- **Latency**: 35 tokens/second on Apple Silicon / modern CPU.
