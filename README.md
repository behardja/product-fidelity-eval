# product-fidelity-eval

This project demonstrates the product fidelity evaluation.


## Getting started

Once the prerequisites have been met and the user parameters are specified, users can follow the notebooks to run through the guided steps.

### Notebooks

* [notebooks/product_fidelity_eval_with_gecko.ipynb](./notebooks/product_fidelity_eval_with_gecko.ipynb) : This notebook illustrates how to assess product image fidelity by using Gemini to create a detailed ground-truth description of a reference image, which then serves as the prompt for the rubric-based Gecko evaluation metric to score candidate images.


### Agent

A multi-agent pipeline that generates product images and evaluates their fidelity against the original using Gecko scoring. Products that fail the threshold are automatically retried (N times) and/or flagged for human review with results aggregated into a final report.

![agent_flow.jpg](./agent/imgs/agent_flow.jpg)

  - For Each Product - outer loop container with Root Agent                                                                                                                             
  - Sequence Agent - wraps the sequential workflow containing:                                                                                                                          
    - Step 1: Parallel Agent - runs both description and image generation concurrently                                                                                                  
    - Step 2: Product Fidelity Evaluation Agent - scores with Gecko                                                                                                                     
    - Threshold decision - routes to pass/retry/fail                                                                                                                                    
    - Retry loop - feeds back to image generation only                                                                                                                                  
  - Final Report - aggregates all results  

### Prerequisites

Ensure the project environment, network settings, and service accounts used have the appropriate Google Cloud authentication and permissions to access the following services:
- `Vertex AI`
- `Cloud Storage`
- `Artifact Registry`