# AWSense: Team Role & Responsibility Matrix

This document outlines the overarching responsibilities for our 5-person engineering team. 

Because the project begins without access to the AWS Sandbox, the responsibilities are designed to allow immediate development using **Mock Data**, transitioning smoothly into **Live AWS Integration** once access is granted.

---

## 1. Frontend UI/UX Engineer
**Core Responsibility:** Own the visual presentation, user experience, and overarching dashboard architecture.
* **Pre-AWS Sandbox:** Scaffold the React (Next.js/Vite) application. Implement the design system (e.g., Tailwind CSS, dark mode, glassmorphism). Build the static layouts, charts, data tables, and navigation structures.
* **AWS Integration Phase:** Refine UI components to gracefully handle edge cases in live data (e.g., extremely long resource IDs, missing metadata). Implement real-time UI updates for live security alerts.

## 2. Frontend State & Integration Engineer
**Core Responsibility:** Own the data layer of the frontend, state management, and communication with the backend API.
* **Pre-AWS Sandbox:** Establish the global state management strategy (Redux, Zustand, Context). Build the API client layer to consume static JSON contracts and hook the UI components to this mock data.
* **AWS Integration Phase:** Transition the API client to hit live backend endpoints. Implement WebSockets or polling for live data updates. Build robust error handling for API timeouts or AWS rate limiting.

## 3. Backend Data & Cloud Engineer
**Core Responsibility:** Own the ingestion of telemetry data, mock data generation, and AWS integration.
* **Pre-AWS Sandbox:** Build a Python-based "Mock Engine" that generates statistically realistic CloudWatch metrics, CloudTrail logs, and billing data containing intentional anomalies.
* **AWS Integration Phase:** Deprecate the Mock Engine. Configure cross-account IAM roles. Write the `boto3` scripts to pull real telemetry. Set up AWS EventBridge or SQS to stream live events directly into the backend.

## 4. Backend API & Database Engineer
**Core Responsibility:** Own the FastAPI server, database architecture, and data serving logic.
* **Pre-AWS Sandbox:** Design the database schemas (PostgreSQL for application state, MongoDB/Elasticsearch for high-volume logs). Build the REST API endpoints and connect them to the Mock Engine.
* **AWS Integration Phase:** Optimize database indexing and write-speeds to handle massive influxes of real AWS logs. Update endpoints to query the live database. Handle the cloud deployment of the backend services (e.g., ECS or App Runner).

## 5. Machine Learning & AI Engineer
**Core Responsibility:** Own the anomaly detection algorithms, correlation logic, and LLM integration.
* **Pre-AWS Sandbox:** Ingest the fake data from the Mock Engine. Build and train anomaly detection models (e.g., `IsolationForest` via Scikit-learn) to identify the intentional anomalies. Write the base LLM prompts for generating human-readable summaries.
* **AWS Integration Phase:** Validate and tune the ML models against live, noisy AWS data to minimize false positives. Connect live security alerts to the LLM backend to generate real-time, actionable incident reports. Implement the final Risk Scoring algorithm.
