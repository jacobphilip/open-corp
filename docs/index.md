# open-corp

**AI-powered operations with specialist workers, budget controls, and persistent memory.**

open-corp is a framework for building and managing teams of AI workers. Each worker has their own personality, skills, knowledge base, and performance history. A budget-aware accountant ensures costs stay under control, while a router handles model selection and failover.

## Features

- **Specialist Workers** — Hire, train, and manage AI agents with distinct roles and personalities
- **Budget Controls** — Automatic cost tracking with daily limits and threshold alerts
- **Multi-Model Routing** — Tier-based model selection with automatic fallback
- **Knowledge Training** — Train workers from documents, URLs, and YouTube videos
- **DAG Workflows** — Define multi-step pipelines with parallel execution
- **Smart Task Routing** — Auto-select the best worker for a task based on skills and performance
- **Self-Optimizing** — Auto-promote/demote workers based on performance analytics
- **Multi-Operation Management** — Switch between multiple projects seamlessly
- **Template Marketplace** — Browse and install worker templates from a remote registry
- **Scheduling** — Cron, interval, and one-time task scheduling with daemon support
- **Webhooks** — HTTP API for triggering tasks externally with rate limiting and payload validation
- **Dashboard** — Local web dashboard with HTML pages and JSON API, optional auth
- **Security** — Input validation, secret redaction, rate limiting, atomic writes, dashboard authentication
- **Paper Trading** — Built-in broker for simulated stock trading workflows

## Quick Example

```bash
# Initialize a project
corp init

# Hire a worker from a template
corp hire researcher alice

# Chat with your worker
corp chat alice

# Run a workflow
corp workflow run workflows/pipeline.yaml

# Review team performance
corp review
```

## Version

Current version: **1.3.0**
