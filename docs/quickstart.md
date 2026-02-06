# Quickstart

Get up and running with open-corp in 10 minutes.

## Installation

```bash
pip install open-corp
```

For development:

```bash
git clone https://github.com/open-corp/open-corp
cd open-corp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Initialize a Project

```bash
corp init
```

You'll be prompted for:

- **Project name** — identifies your operation
- **Owner name** — who runs this project
- **Mission statement** — what the project does
- **Daily budget** — maximum daily API spend (USD)
- **OpenRouter API key** — get one at [openrouter.ai](https://openrouter.ai)

This creates `charter.yaml`, `.env`, and the `workers/`, `templates/`, and `data/` directories.

## Hire a Worker

From a template:

```bash
corp hire researcher alice
```

From scratch:

```bash
corp hire unused bob --scratch --role analyst
```

## Chat with a Worker

```bash
corp chat alice
```

Type messages, get responses. Type `quit` to exit. Sessions are automatically summarized and stored in the worker's memory.

## Train a Worker

```bash
# From a document
corp train alice --document data/report.pdf

# From a URL
corp train alice --url https://example.com/article

# From YouTube
corp train alice --youtube https://youtube.com/watch?v=abc123
```

## Check Status

```bash
# Project overview
corp status

# Detailed budget report
corp budget

# List all workers
corp workers

# Inspect a worker
corp inspect alice
```

## Run a Workflow

Create a workflow YAML file:

```yaml
name: research-pipeline
description: Research and summarize a topic
nodes:
  research:
    worker: alice
    message: "Research the latest trends in AI"
  summarize:
    worker: alice
    message: "Summarize: {research.output}"
    depends_on: [research]
```

Run it:

```bash
corp workflow run workflows/research-pipeline.yaml
```

## Next Steps

- [CLI Reference](user-guide/cli.md) — all commands and options
- [Configuration](user-guide/configuration.md) — charter.yaml field reference
- [Templates](user-guide/templates.md) — creating custom worker templates
- [Workflows](user-guide/workflows.md) — DAG workflow syntax and parallel execution
