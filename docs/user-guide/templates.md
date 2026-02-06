# Templates

Templates are pre-configured worker profiles that can be used to quickly hire specialized workers.

## Template Structure

Each template lives in `templates/<name>/` with these files:

```
templates/researcher/
  profile.md       # Personality, background, communication style
  skills.yaml      # Role and skill list
  config.yaml      # Level, model preferences, context budget
```

### profile.md

Markdown file defining the worker's personality:

```markdown
# Researcher

You are a meticulous research analyst with expertise in data gathering
and synthesis. You cite sources, note confidence levels, and clearly
distinguish between facts and speculation.
```

### skills.yaml

```yaml
role: researcher
skills:
  - research
  - analysis
  - data gathering
  - source verification
```

### config.yaml

```yaml
level: 1
max_context_tokens: 2000
model: "deepseek/deepseek-chat"
```

## Built-in Templates

| Template | Role | Description |
|----------|------|-------------|
| researcher | Research | Information gathering and analysis |
| content-repurposer | Content | Transforms content across formats |
| job-hunter | Career | Resume optimization and job search |
| data-analyst | Analytics | Data processing and visualization |
| content-writer | Writing | Articles, copy, documentation |
| trader | Finance | Market analysis and trading strategies |

## Creating Custom Templates

1. Create a directory in `templates/`:
   ```bash
   mkdir templates/my-specialist
   ```

2. Write `profile.md` with the worker's personality and expertise

3. Define skills in `skills.yaml`

4. Set configuration in `config.yaml`

5. Hire from your template:
   ```bash
   corp hire my-specialist worker-name
   ```

## Marketplace

Browse and install community templates from a remote registry:

```bash
# Configure registry URL in charter.yaml
# marketplace:
#   registry_url: "https://example.com/registry.yaml"

# Browse available templates
corp marketplace list

# Search by keyword
corp marketplace search "trading"

# View details
corp marketplace info researcher

# Install
corp marketplace install researcher
```

### Registry Format

The marketplace registry is a YAML file hosted at any URL:

```yaml
templates:
  - name: researcher
    description: "Research specialist for information gathering"
    author: "open-corp"
    tags: [research, analysis, data]
    url: "https://raw.githubusercontent.com/open-corp/marketplace/main/templates/researcher"
```

The `url` field points to a directory containing `profile.md`, `skills.yaml`, and optionally `config.yaml`.
