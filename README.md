# AWSense

## Overview
AWSense is an intelligent cloud management and security platform designed to continuously monitor, optimize, and secure AWS infrastructure. 

The platform bridges the gap between cloud security posture management (CSPM) and cloud financial management (FinOps). By ingesting and correlating signals across multiple AWS services—such as resource configuration, user activity, network traffic, and billing—AWSense identifies inefficiencies, abnormal resource consumption, and potential security incidents.

## Problem Statement
Modern AWS environments generate vast amounts of siloed telemetry. A CloudWatch alarm for high CPU, a CloudTrail event for an unusual IAM login, and a sudden spike in Cost Explorer may appear unrelated when analyzed independently. AWSense aggregates and correlates these events to provide actionable context, identifying complex scenarios such as compromised credentials resulting in unauthorized compute provisioning.

## Core Capabilities
1. **Resource Optimization:** Continuous evaluation of EC2, EBS, S3, and RDS to identify underutilized instances, unattached storage, and over-provisioned infrastructure.
2. **Behavioral Anomaly Detection:** Establishes behavioral baselines for IAM principals and AWS resources. Evaluates deviations using statistical analysis and machine learning.
3. **Automated Traffic Analysis:** Analyzes network and application traffic patterns to identify automated bots or scrapers impacting infrastructure costs.
4. **Intelligent Event Correlation:** Cross-references security, performance, and billing telemetry to build unified incident narratives.
5. **Contextual Risk Scoring:** Aggregates individual anomalies into a unified risk score based on resource criticality, cost impact, and behavioral deviation.

## System Architecture

The AWSense architecture is designed around a decoupled data ingestion and analysis pipeline.

### 1. Data Ingestion Layer
- **AWS API Integration:** Uses `boto3` to interact with AWS services via a cross-account IAM role with strict read-only permissions.
- **Log Aggregation:** Pulls event data from CloudTrail, CloudWatch Metrics/Logs, and Cost Explorer.
- **Mock Data Engine:** (Pre-production) A local data generator simulating AWS telemetry for local development and ML model training prior to sandbox access.

### 2. Processing & Storage Layer
- **Relational Data (PostgreSQL):** Stores application state, user configurations, resource inventories, and historical baselines.
- **Time-Series / Document Data (Elasticsearch / MongoDB):** Handles high-volume event logs, traffic data, and raw CloudTrail events.
- **Correlation Engine:** A Python-based microservice that evaluates incoming telemetry against defined rulesets and historical baselines.

### 3. Machine Learning & Analytics Engine
- **Anomaly Detection:** Utilizes Scikit-learn (e.g., Isolation Forests, K-Means clustering) to detect deviations in time-series metrics (CPU, Network In/Out) and API call frequencies.
- **AI Analysis:** Integrates with an LLM backend to parse correlated incidents and generate human-readable explanations and remediation steps.

### 4. Presentation Layer
- **Frontend Application:** A React-based Single Page Application (Next.js/Vite) providing the primary user interface.
- **Dashboard Interfaces:** Displays global risk scores, cost-saving opportunities, and granular security alerts through a unified control plane.

## Development Workflow (Pre-AWS Sandbox)

While awaiting provisioning of the AWS testing sandbox, development is structured around the following parallel tracks:

1. **Mock Data Generation (Backend):** Developing Python generators to output realistic JSON structures mirroring AWS CloudTrail, CloudWatch, and Billing APIs.
2. **Frontend Implementation:** Building out the dashboard UI components and state management using the mock data schemas.
3. **Database Schema Design:** Normalizing the relational schema for resources and establishing the indexing strategy for event data.
4. **ML Prototyping:** Training baseline anomaly detection models using the synthesized AWS data.

## Getting Started

*(Setup instructions for the local environment, database containers, and the frontend/backend servers will be documented here.)*