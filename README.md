# product-fidelity-eval

This project demonstrates the product fidelity evaluation.


## Getting started

Once the prerequisites have been met and the user parameters are specified, users can follow the notebooks to run through the guided steps.

### Notebooks

* [notebooks/product_fidelity_eval_with_gecko.ipynb](./notebooks/product_fidelity_eval_with_gecko.ipynb) : This notebook illustrates how to assess product image fidelity by using Gemini to create a detailed ground-truth description of a reference image, which then serves as the prompt for the rubric-based Gecko evaluation metric to score candidate images.


### Agent

A multi-agent pipeline that generates product images and evaluates their fidelity against the original using Gecko scoring. Products that fail the threshold are automatically retried (N times) and/or flagged for human review with results aggregated into a final report.

![agent_flow.jpg](./product_fidelity_agent/imgs/agent_flow.png)

  - For Each Product - outer loop container with Root Agent                                                                                                                             
  - Sequence Agent - wraps the sequential workflow containing:                                                                                                                          
    - Step 1: Parallel Agent - runs both description and image generation concurrently                                                                                                  
    - Step 2: Product Fidelity Evaluation Agent - scores with Gecko                                                                                                                     
    - Threshold decision - routes to pass/retry/fail                                                                                                                                    
    - Retry loop - feeds back to image generation only                                                                                                                                  
  - Final Report - aggregates all results  

### Front-End App

A React dashboard with two panels: a GCS image browser on the left and an agent chat on the right. Select a product image from GCS, click Evaluate, and watch the agent pipeline run in real time via SSE streaming.

#### Getting Started

**Prerequisites:**
- Node.js (v18+)
- Python 3.10+
- Google Cloud authentication (`gcloud auth application-default login`)
- Access to Vertex AI, Cloud Storage, and Artifact Registry

**1. Install Python dependencies:**

```bash
pip install -r requirements.txt
```

**2. Install front-end dependencies:**

```bash
cd app
npm install
```

**3. Start the backend server (terminal 1):**

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

This starts the custom FastAPI server that wraps the ADK agent and adds GCS proxy endpoints.

**4. Start the front-end dev server (terminal 2):**

```bash
cd app
npm run dev
```

The app opens at [http://localhost:3000](http://localhost:3000).

**5. Using the app:**

1. Enter a GCS prefix in the search bar (e.g. `gs://your-bucket/product-images/`) and click **Browse**
2. Click an image to select it
3. Click **Evaluate** to send the image to the agent for fidelity evaluation
4. Watch the agent response stream in the chat panel on the right
5. You can also type free-form messages in the chat input

### Prerequisites

Ensure the project environment, network settings, and service accounts used have the appropriate Google Cloud authentication and permissions to access the following services:
- `Vertex AI`
- `Cloud Storage`
- `Artifact Registry`
