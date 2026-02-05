# Facebook Post — open-corp Launch Announcement

## Option A: The Hook (Recommended)

---

I've been building something for the last few months and I'm ready to talk about it.

It's called open-corp — an open source framework that lets you hire, train, and manage a team of AI workers.

Not a chatbot you babysit. An actual team of AI specialists that run on schedules, remember what they've learned, build on previous work, and cost pennies per task.

Here's the problem with just using ChatGPT or Claude: it's one conversation that forgets everything when you close the tab. You re-explain your business every time. You can't run two tasks at once. There's no budget visibility. And it waits for you to show up — it never works while you're not there.

open-corp fixes all of that.

Your project folder is your operation. Claude Code (or any LLM via OpenRouter) is your interface — it reads a config file, understands your project, and acts on your behalf. You can hire workers for specific jobs. Train them from YouTube playlists — the system watches the videos, extracts the person's knowledge and style, and turns that into a worker with real expertise.

There's a hard budget guardrail that tracks every cent. It runs before every API call. Over limit? The call doesn't happen. No surprise bills. You see exactly where every dollar goes.

And when you need a second opinion, you consult a Board of Advisors — Grok for real-time data, ChatGPT for stress-testing, Claude for deep reasoning. One brain is smart. A coordinated team is smarter.

I built an automated trading analysis desk as the showcase. But the framework is general-purpose — research teams, content creation, data analysis, job hunting, marketing automation, whatever your business needs.

Cost: $20/month minimum. Full setup with all three advisors: ~$70/month. The AI workers themselves cost fractions of a cent per task.

You interact through a terminal. If you've never used one, it takes 20 minutes to learn. The payoff is an entire AI workforce under your control.

Private on GitHub while I finish v0.1. If you're interested — comment or DM me.

The future of productivity isn't one AI assistant. It's an AI workforce that works for you.

🔗 github.com/jacobphilip/open-corp

---

## Option B: The Short Version

---

Built an open source project called open-corp.

The problem: ChatGPT/Claude is one conversation that forgets everything, can't multitask, and never works when you're not there.

The solution: A framework that lets you hire a team of AI specialists. They have persistent memory, run on schedules, and operate under strict budget controls — a hard guardrail that blocks API calls when you're over budget. You manage them through Claude Code (or any LLM via OpenRouter). They work 24/7.

I built an automated trading desk as the example. But it works for anything — research, content creation, data analysis, marketing automation, whatever your business needs.

$20-70/month. Open source. Going public on GitHub soon.

DM me if you want early access.

---

## Option C: The Technical Angle (for your developer friends)

---

Shipping a new open source framework: open-corp

TL;DR: Claude Code as the interface to an AI agent corporation. OpenRouter for cost-controlled model routing ($3/day budget, CFO agent enforces it). Multi-AI Board of Directors (Grok for real-time data, ChatGPT for stress-testing, Claude for reasoning). Employees with persistent memory, seniority levels, and domain expertise trained from YouTube transcriptions via Whisper + DeepSeek V3.

The trading example ships with ICT (trained from 51 videos, Level 5 Principal) and Caleb (Level 2 Junior, runs on systemd timers during London/NY kill zones).

But the framework is domain-agnostic. Each corporation is a self-contained directory with a charter, employees, budget tracker, and git sync.

Stack: Python, OpenRouter, Claude Code, YAML configs, TinyDB for state, yt-dlp + Whisper for the training pipeline.

Built on agentic engineering principles — plan before code, verify before done, honest AI (employees admit when they don't know), self-improvement loops.

Private repo for now, going public after v0.1 stabilizes. Star/watch if interested: github.com/jacobphilip/open-corp

---

## Suggested Image/Visual

Consider creating a simple diagram showing:

```
YOU (Owner)
    ↓
  CEO ← Board (Grok, ChatGPT, Claude)
    ↓
  CFO + Employees
```

A clean version of this as an image would make the post much more shareable. You could ask Claude to generate this as an SVG or use a tool like Excalidraw.
