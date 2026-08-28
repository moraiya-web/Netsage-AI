# NetSage AI

### An AI Troubleshooting Helper with Human Review

NetSage AI is an intelligent Cisco network troubleshooting system designed to assist in identifying and analyzing common network problems.

The project combines deterministic rule-based validation with AI-assisted diagnosis and mandatory human review. The system uses network telemetry, observed symptoms, topology information, OSI-layer context, severity, and troubleshooting evidence to produce a structured diagnosis.

The main objective is not to blindly accept an AI-generated answer, but to provide an evidence-based troubleshooting workflow in which the final diagnosis can be reviewed, accepted, edited, or rejected by a human.

---

## Project Objectives

The project is designed to:

- Identify common Cisco networking problems from troubleshooting evidence.
- Organize network issues according to their category, severity, and OSI layer.
- Analyze captured CLI / telemetry output.
- Use deterministic rules to validate common configuration mistakes.
- Generate structured troubleshooting diagnoses.
- Present the probable root cause and supporting evidence.
- Provide suggested next troubleshooting steps and fixes.
- Allow a human reviewer to verify the proposed diagnosis.
- Record human decisions for traceability and responsible AI evaluation.
- Provide dashboard-level summaries of troubleshooting cases and AI-human agreement.

---

## Key Features

### 1. Network Troubleshooting Cases

The system supports a structured collection of network troubleshooting scenarios.

Each case can contain information such as:

- Case ID
- Network category
- Severity
- Observed symptom
- Topology context
- Captured CLI / telemetry output
- Expected fault
- OSI layer
- Networking concept

---

### 2. Evidence-First Diagnosis

NetSage AI follows an evidence-first troubleshooting approach.

Instead of relying only on a generated answer, the system considers the available troubleshooting evidence such as:

- Device output
- Network symptoms
- Topology information
- Configuration-related observations
- Expected fault
- OSI-layer context

This makes the diagnosis more explainable and easier to review.

---

### 3. Deterministic Rule Checker

The project includes rule-based validation for common networking mistakes.

The rule checker provides a deterministic layer of validation before or alongside AI-assisted reasoning.

This helps identify situations where an AI-generated diagnosis may not agree with the actual evidence.

---

### 4. AI-Assisted Troubleshooting

The project provides an AI-assisted troubleshooting workflow for interpreting network evidence and producing a structured diagnosis.

The AI output can include:

- Probable root cause
- Confidence
- Evidence supporting the diagnosis
- Suggested next command
- Recommended fix

The AI result is treated as a proposed diagnosis rather than an automatically accepted final answer.

---

### 5. Human Review

Human review is an important part of the system.

A reviewer can:

- Accept the proposed diagnosis.
- Edit/correct the diagnosis.
- Reject the proposed diagnosis.
- Add reviewer notes.

This prevents an incorrect AI response from being automatically treated as the final troubleshooting result.

---

### 6. Responsible AI Logging

Human decisions are recorded for traceability.

The project maintains information related to:

- Case ID
- AI verdict
- Corrected diagnosis
- Reviewer notes
- Review timestamp

This allows the project to evaluate cases where the AI diagnosis was accepted, modified, or rejected by a human.

---

### 7. Dashboard

The dashboard provides a summary of the troubleshooting dataset.

It can be used to analyze:

- Issue categories
- Severity distribution
- OSI-layer distribution
- Rule-checker coverage
- AI vs. human agreement
- Reviewed cases

The dashboard helps visualize the overall performance and behavior of the troubleshooting system.

---
## System Workflow

The overall workflow of NetSage AI is:

```text
Network Troubleshooting Case
            |
            v
   Collect Evidence
            |
            v
 CLI / Telemetry + Symptom + Topology
            |
            v
   Deterministic Rule Check
            |
            v
    AI-Assisted Diagnosis
            |
            v
 Root Cause + Evidence + Confidence
            |
            v
       Human Review
        /    |    \
       /     |     \
   Accept   Edit   Reject
       \     |     /
        \    |    /
         v   v   v
     Final Reviewed Result
            |
            v
      Responsible AI Log
            |
            v
         Dashboard

## Run on Windows
1. Install Python 3.10+.
2. Open this folder in CMD/PowerShell.
3. Run:
   `python -m pip install -r requirements.txt`
4. Run:
   `python -m streamlit run app.py`
5. Open the localhost URL shown by Streamlit (normally http://localhost:8501).

You can also double-click `run.bat`.
