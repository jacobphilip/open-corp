# Workflows

Workflows define multi-step DAG pipelines where each node is a task assigned to a worker.

## YAML Format

```yaml
name: research-pipeline
description: Research and synthesize information

nodes:
  gather:
    worker: alice
    message: "Research recent developments in quantum computing"

  analyze:
    worker: bob
    message: "Analyze these findings: {gather.output}"
    depends_on: [gather]

  summarize:
    worker: alice
    message: "Write a summary based on: {analyze.output}"
    depends_on: [analyze]
    condition: "success"
```

## Node Fields

| Field | Required | Description |
|-------|----------|-------------|
| `worker` | Yes | Worker name or `"auto"` for smart routing |
| `message` | No | Task message (supports output substitution) |
| `depends_on` | No | List of node IDs that must complete first |
| `condition` | No | `"success"` (default) or `"contains:keyword"` |

## Output Substitution

Use `{node_id.output}` to inject the output of a previous node:

```yaml
nodes:
  step1:
    worker: alice
    message: "Generate a list of topics"
  step2:
    worker: bob
    message: "Expand on these topics: {step1.output}"
    depends_on: [step1]
```

Outputs are truncated to 2000 characters per node.

## Conditions

### success (default)

Node runs only if all dependencies completed successfully:

```yaml
step2:
  worker: bob
  message: "Continue processing"
  depends_on: [step1]
  condition: "success"
```

### contains:keyword

Node runs if any dependency output contains the keyword (case-insensitive):

```yaml
alert:
  worker: alice
  message: "Investigate the anomaly"
  depends_on: [analysis]
  condition: "contains:anomaly"
```

## Parallel Execution

Nodes at the same depth level execute in parallel using a thread pool:

```yaml
nodes:
  # Depth 0 — runs in parallel
  research_a:
    worker: alice
    message: "Research topic A"
  research_b:
    worker: bob
    message: "Research topic B"

  # Depth 1 — runs after both complete
  merge:
    worker: alice
    message: "Merge findings: {research_a.output} and {research_b.output}"
    depends_on: [research_a, research_b]
```

## Smart Worker Routing

Use `worker: auto` to let the TaskRouter select the best worker:

```yaml
nodes:
  analyze:
    worker: auto
    message: "Analyze market trends for Q4"
```

The router scores workers by skill match (50%), performance rating (35%), and seniority (15%).

## Running Workflows

```bash
# Run a workflow
corp workflow run workflows/pipeline.yaml

# List past runs
corp workflow list
corp workflow list --name research-pipeline

# Check run status
corp workflow status <run_id>
```

## Diamond DAG Example

```yaml
name: diamond
description: Fan-out and fan-in pattern

nodes:
  start:
    worker: alice
    message: "Generate initial data"

  branch_a:
    worker: bob
    message: "Process branch A: {start.output}"
    depends_on: [start]

  branch_b:
    worker: carol
    message: "Process branch B: {start.output}"
    depends_on: [start]

  merge:
    worker: alice
    message: "Merge results: {branch_a.output} + {branch_b.output}"
    depends_on: [branch_a, branch_b]
```
