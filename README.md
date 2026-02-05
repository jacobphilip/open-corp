# open-corp

**An AI workforce that works while you don't. For $20–70/month.**

open-corp is an open source framework for building AI-powered operations. You talk to your project through Claude Code (or any LLM via OpenRouter). The LLM understands your project, delegates to specialist workers you've trained, and operates under strict budget controls.

You give tasks. Workers execute. You review results.

The project folder *is* your operation. Claude Code *is* your interface. No extra abstractions.

---

## Why Not Just Use ChatGPT?

Because a single chatbot — no matter how smart — is still just one conversation that forgets everything when you close the tab.

Here's what open-corp gives you that a frontier model alone doesn't:

**Persistent memory.** Your workers remember yesterday's work. They build on last week's research. They don't ask you to re-explain your business every session.

**Specialization.** A single model tries to be everything to everyone. open-corp lets you train specialists — a researcher who knows your industry, a writer who matches your brand voice, an analyst who understands your metrics. Each worker is tuned to their job.

**Parallel work.** You can't ask ChatGPT to research competitors, draft a proposal, AND analyze your sales data at the same time. open-corp workers operate independently. One researches while another writes while a third crunches numbers.

**Automation.** ChatGPT waits for you to show up. open-corp workers run on schedules — scanning markets at 9:30 AM, generating reports at 5 PM, pulling news every hour. They work while you sleep.

**Cost control.** One GPT-4 conversation can burn through tokens fast with no visibility. open-corp has a built-in Accountant that tracks every cent, throttles spending automatically, and hard-stops before your budget is hit. The Accountant is a guardrail, not an agent — it cannot be bypassed or forgotten.

**Multi-AI intelligence.** Instead of being locked into one model's strengths and blind spots, open-corp routes to the right AI for the job — cheap models for simple tasks, powerful models for complex ones, and optionally consults Grok for real-time data and ChatGPT for stress-testing. One brain is smart. A coordinated team is smarter.

**Model flexibility.** Don't want to use Claude? Configure OpenRouter to use Kimi 2.5, DeepSeek, or any model that fits your budget. The framework doesn't care — it works with whatever LLM you point it at.

The difference is the same as hiring one generalist intern versus building a small company. Both can help. Only one scales.

---

## Who Is This For?

Ambitious people who run a business, manage projects, or just want to get more done.

You should have at least a high school education and a willingness to type commands into a terminal. That's the interface. If you've never used one, there are plenty of tutorials online — it takes about 20 minutes to learn the basics. If that's not for you, that's fine, but this tool rewards people who are willing to learn.

What you get in return: an AI workforce that costs pennies per task, runs on your schedule, and compounds knowledge over time.

---

## What Can It Do?

open-corp is a general-purpose framework. Here are some things people are building:

| Use Case | What It Does |
|----------|-------------|
| **Research assistant** | Finds, reads, and summarizes information on any topic |
| **Content repurposer** | Takes a YouTube video and turns it into blog posts, tweets, and summaries |
| **Trading desk** | Scans markets, identifies setups, paper trades automatically (example included) |
| **Freelance assistant** | Drafts proposals, client emails, invoices |
| **Job hunter** | Searches listings, tailors resumes, tracks applications |
| **Data analyst** | Crunches numbers, finds patterns, generates reports |

The framework doesn't care what domain you use it for. You define the mission. The AI workers execute.

---

## How It Works

```
┌─────────────────────────────────────────────────────┐
│                    YOU (Owner)                       │
│           Terminal (Claude Code) or Telegram         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Your LLM (via CLAUDE.md)                │
│      Claude / Kimi 2.5 / DeepSeek / any model        │
│                                                      │
│   • Understands your project structure               │
│   • Delegates to Workers                             │
│   • Consults Board when needed                       │
│   • All spending goes through Accountant first       │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Accountant  │ │   Workers    │ │    Board     │
│  (Guardrail) │ │ (Specialists)│ │  (Advisors)  │
│              │ │              │ │              │
│ Hard budget  │ │ You train    │ │ • Grok       │
│ limit — runs │ │ these for    │ │ • ChatGPT    │
│ before EVERY │ │ specific     │ │ • Claude     │
│ API call     │ │ jobs         │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

**The project folder is your operation.** The charter, workers, memory, and budget all live there.

**Claude Code (or any LLM) is your interface.** It reads CLAUDE.md, understands the project, and acts on your behalf. You can swap models via OpenRouter — the framework doesn't care which LLM you use.

**The Accountant is infrastructure, not an agent.** It wraps every API call. Before tokens are spent, it checks the budget. Over limit? The call doesn't happen. This runs regardless of what the LLM decides — it's a hard guardrail that cannot be bypassed.

**Workers are specialists you hire and train.** From templates, from YouTube playlists, from documents. Each has their own memory, skills, and personality.

**The Board is optional.** Grok for real-time data, ChatGPT for stress-testing, Claude for deep reasoning. Consult them when you need a second opinion.

---

## What You Need

### Required

| What | Cost | Why |
|------|------|-----|
| [Claude Pro](https://claude.ai/pro) | $20/month ($17/mo annual) | Your main interface — Claude Code is included with Pro |
| [OpenRouter](https://openrouter.ai) | Pay-per-use (~$1–3/day typical) | Powers your workers with cheap AI models |
| [GitHub](https://github.com) | Free | Stores your project files and history |

**Minimum total: ~$20–30/month** depending on how much your workers think.

### Optional (adds Board of Advisors)

| What | Cost | Why |
|------|------|-----|
| [Grok Super](https://x.ai) | $30/month | Advisor — real-time data, current prices, breaking news |
| [ChatGPT Plus](https://chat.openai.com) | $20/month | Advisor — stress-testing ideas, finding holes in plans |

**Full setup: ~$70/month** (plus OpenRouter usage)

The advisors are optional. Your operation works fine without them. But having a second and third opinion makes better decisions — same as in real business.

### Cost Safety

This is important: **you control the spending.**

- OpenRouter lets you set hard daily limits in your account settings
- The Accountant (CFO agent) tracks every cent and pauses operations before overspending
- You pre-fund your OpenRouter account — no surprise credit card charges
- Budget thresholds: 🟢 Normal → 🟡 Caution → 🟠 Austerity → 🔴 Frozen

Set your OpenRouter daily limit to $5 and you literally cannot overspend. The system is designed to fail safe, not fail expensive.

---

## Quick Start (15 minutes)

### Step 1: Get Your Accounts Ready

1. **Claude Pro** ($20/month) — Sign up at [claude.ai](https://claude.ai), upgrade to Pro. Then install Claude Code — open your terminal and run the install command from [Anthropic's docs](https://docs.anthropic.com/en/docs/claude-code). One-line install, no extra software needed.
2. **OpenRouter** (pay-per-use) — Sign up at [openrouter.ai](https://openrouter.ai). Add $5 credit to start. Go to "Keys" → "Create Key" → copy it (starts with `sk-or-v1-...`). Then go to Settings → Limits → set a daily limit.
3. **GitHub** (free) — Sign up at [github.com](https://github.com). Create a private repository for your operation.

### Step 2: Clone and Set Up

Open your terminal and run:

```bash
# Download the framework
git clone https://github.com/jacobphilip/open-corp.git
cd open-corp

# Copy the example configuration
cp .env.example .env

# Open .env and paste your OpenRouter API key
nano .env
```

In the `.env` file, replace `your-key-here` with your actual OpenRouter API key:

```
OPENROUTER_API_KEY=sk-or-v1-your-actual-key-here
```

Save and close (Ctrl+X, then Y, then Enter).

### Step 3: Install the Framework

```bash
# Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Step 4: Hire a Worker and Start

```bash
# Check project status
python scripts/corp.py status

# Hire a researcher from template
python scripts/corp.py hire researcher my-researcher

# See your workers
python scripts/corp.py workers

# Chat with your worker (requires OPENROUTER_API_KEY in .env)
python scripts/corp.py chat my-researcher
```

That's it. You're the Owner. Start giving orders.

---

## How It Works

### Worker Seniority

Workers start as interns and get promoted based on performance:

| Level | Title | What They Can Do |
|-------|-------|------------------|
| 1 | Intern | Simple tasks, asks for confirmation |
| 2 | Junior | Basic work, handles simple tasks alone |
| 3 | Senior | Handles most tasks independently |
| 4 | Lead | Can coordinate junior workers |
| 5 | Principal | Strategic input, influences big decisions |

Higher-level workers have access to smarter (more expensive) AI models. The Accountant monitors this.

### Budget Control

The Accountant tracks every cent. Hard limits — no runaway spending:

| Spending | Status | What Happens |
|----------|--------|--------------|
| Under 60% | 🟢 Normal | Full speed ahead |
| 60–80% | 🟡 Caution | Prefers cheaper AI models |
| 80–95% | 🟠 Austerity | Only essential tasks, you're notified |
| 95–100% | 🔴 Critical | Everything pauses, you're notified |
| Over 100% | ⛔ Frozen | Nothing runs. Period. |

**Plus:** OpenRouter has its own server-side daily limit. Even if the software has a bug, your credit card is protected. Belt and suspenders.

---

## Example: Trading Desk (Advanced)

> **Disclaimer:** This is an educational example of the framework's capabilities. It uses paper trading (fake money) by default. Automated trading carries real financial risk. If you enable live trading, you are responsible for any losses. This is not financial advice. open-corp is not a financial product.

The repo includes a complete example operation: **an ICT (Inner Circle Trader) analysis desk.**

This example shows you how to:
- **Hire from YouTube** — Download a playlist, transcribe it, extract expertise into a worker personality
- **Train workers** — Build knowledge bases from video content
- **Deploy automated scanning** — Market analysis during key trading sessions
- **Track everything** — Paper trading with full audit trails

### What's In the Example

| Worker | Role | How They Were Created |
|--------|------|---------------------|
| ICT | Master Strategist | Trained from 51 YouTube videos |
| Caleb | Junior Analyst | Executes paper trades based on ICT's methodology |

### Automated Schedule

The example configures timers to scan markets during key sessions:

| Session | Time (EST) | What Happens |
|---------|------------|--------------|
| London Open | 2:00–5:00 AM | Scan for setups |
| NY AM | 9:30–12:00 PM | Primary analysis window |
| NY PM | 1:00–4:00 PM | Afternoon opportunities |

### Important: Trading is Paper-Only by Default

The `paper_trading: true` setting in the charter cannot be changed to `false` without explicitly editing the config and acknowledging the risk. This is intentional. The framework is designed to analyze and learn first, execute later — and only when you've validated the strategy yourself.

**You don't have to build a trading operation.** This is just the most complex example. Your project can do anything — research, writing, data analysis, content creation, job hunting, whatever you need.

---

## Project Structure

```
open-corp/
├── CLAUDE.md                    # Agentic engineering philosophy (read by Claude Code)
├── README.md                    # You're reading this
├── CHANGELOG.md                 # Release history
├── ROADMAP.md                   # What's planned
├── TEST_PLAN.md                 # Test inventory
├── charter.yaml                 # Project configuration (budget, models, worker defaults)
├── .env.example                 # Template for API keys
├── pyproject.toml               # Python packaging and install config
├── requirements.txt             # Python dependencies
│
├── framework/                   # Core framework code
│   ├── exceptions.py            # Shared exceptions (BudgetExceeded, ModelUnavailable, TrainingError, etc.)
│   ├── config.py                # Project configuration loader (charter.yaml + .env)
│   ├── accountant.py            # Budget guardrail (runs before every API call)
│   ├── router.py                # Model selection, OpenRouter integration, tier fallback
│   ├── knowledge.py             # Knowledge base: chunking, keyword search, validation
│   ├── worker.py                # Worker class (profile, memory, knowledge, skills, chat)
│   └── hr.py                    # Hiring, training (document/web/YouTube), firing, promoting
│
├── scripts/
│   ├── corp.py                  # CLI — init, status, budget, workers, hire, chat, train, inspect, knowledge
│   └── telegram_bot.py          # Telegram bot interface
│
├── templates/                   # Starter worker templates
│   ├── researcher/              # Research specialist
│   ├── content-repurposer/      # Content transformation specialist
│   ├── job-hunter/              # Career assistant
│   ├── data-analyst/            # Data analysis specialist
│   └── content-writer/          # Content writing specialist
│
├── tests/                       # 145 tests (pytest + respx)
│   ├── conftest.py              # Shared fixtures
│   ├── test_config.py           # 7 tests
│   ├── test_accountant.py       # 9 tests
│   ├── test_router.py           # 14 tests
│   ├── test_exceptions.py       # 3 tests
│   ├── test_templates.py        # 5 tests
│   ├── test_worker.py           # 21 tests
│   ├── test_hr.py               # 21 tests
│   ├── test_cli.py              # 31 tests
│   ├── test_knowledge.py        # 23 tests
│   └── test_telegram_bot.py     # 11 tests
│
├── projects/                    # YOUR projects go here
│   └── .gitkeep
│
├── todo.md                      # Task tracker
└── lessons.md                   # Learnings from mistakes
```

---

## Multi-AI Strategy (Board of Advisors)

Each AI brings a different strength:

| Advisor | Strength | When to Consult |
|---------|----------|-----------------|
| **Grok** (via x.ai) | Real-time data, current events, live prices | Anything that changes by the hour |
| **ChatGPT** (via OpenAI) | Stress-testing, structured breakdowns, edge cases | "What could go wrong with this plan?" |
| **Claude** (via Anthropic) | Deep reasoning, synthesis, architecture | Complex decisions, connecting dots across sources |

Consult them directly when you need a second opinion. The CLAUDE.md file includes guidance on when Board consultation is recommended.

---

## Philosophy

open-corp is built on **agentic engineering** principles:

1. **Validate before building** — Define what success looks like before writing any code
2. **Fail fast** — Try things quickly, learn from failures, don't sink time into bad approaches
3. **Iterate** — Ship something small, test it, improve it, repeat
4. **Honest AI** — Workers admit when they don't know something. No fabricated data. Ever.
5. **Budget discipline** — The Accountant is always watching. Every token costs money.

These principles are encoded in the `CLAUDE.md` file that your LLM reads automatically.

---

## Roadmap

| Version | What's New |
|---------|------------|
| **v0.1** | Core framework, CLI, Telegram bot, 2 worker templates, 71 tests |
| **v0.2** | Worker training from documents, web pages, YouTube playlists; knowledge search; 117 tests |
| **v0.3** (current) | `corp init` wizard, multi-turn chat, `corp inspect`, 3 new templates, improved errors; 145 tests |
| **v0.4** | Automated scheduling, worker coordination, chat history truncation |
| **v0.5** | Board of Advisors wiring, broker integrations |
| **v1.0** | Production-ready, self-optimizing operations, community marketplace |

See [ROADMAP.md](ROADMAP.md) for full details.

---

## How Is This Different?

**vs. ChatGPT / Claude / Grok alone:** One conversation, no memory between sessions, no automation, no budget visibility, no specialization. You do all the work. open-corp workers operate independently, on schedules, with persistent memory and strict cost controls. You manage, they execute.

**vs. Zapier / Make.com:** Those chain simple if-then rules together. open-corp workers can reason, handle ambiguity, and adapt. They think, not just trigger.

**vs. AutoGPT / CrewAI / MetaGPT:** Those are developer frameworks written for engineers, often locked to specific models. open-corp is designed for business owners through Claude Code's natural language interface, works with any LLM via OpenRouter, and has budget safety built in from day one.

**vs. being locked to one AI provider:** open-corp doesn't care if you use Claude, Kimi 2.5, DeepSeek, or next month's hot new model. Configure OpenRouter, point it at whatever works, and the framework adapts. Your workers and project structure stay the same.

---

## Contributing

This project is currently in private development. When it goes public, contributions will be welcome.

---

## License

MIT — Use it however you want.

---

## Built By

[Jacob Philip](https://github.com/jacobphilip) — Software engineer building AI-powered automation systems.

Built with the help of Claude, Grok, and ChatGPT. The AI employees eat their own dogfood.
