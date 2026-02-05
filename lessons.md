# Lessons Learned — open-corp

> Patterns and rules derived from experience. Review at session start.

## Format

[YYYY-MM-DD] [context] → [lesson/rule]

## Lessons

[2026-02-05] Project inception → Framework must work with ONLY Claude Pro + OpenRouter. Board members (Grok, ChatGPT) are force multipliers, not dependencies.

[2026-02-05] Target audience → A high-school-educated user should be able to follow the README. If they can't, the docs are wrong — not the user.

[2026-02-05] Inherited from personal-corp → Honest AI is non-negotiable. Employees must admit limitations rather than fabricate data. This was a hard lesson learned during early ICT pipeline development.

[2026-02-05] Inherited from trade-assist → Dual-path architecture works: deliberative (brain) for decisions, reactive (hands) for execution. No LLM in the hot path.

[2026-02-05] Inherited from poly-trade-assist → Define go/no-go metrics before building. If capture ratio < threshold, pivot immediately. No sunk cost fallacy.

[2026-02-05] ChatGPT stress-test → v0.1 target audience is builders/power users, NOT mainstream users. Be honest about this. "Anyone with a high school education" is v0.3+ goal requiring a one-click installer.

[2026-02-05] ChatGPT stress-test → Terminal usage is the #1 abandonment point for non-technical users. 80-90% drop-off. One-click installer is non-negotiable for mainstream adoption (roadmap v0.3).

[2026-02-05] ChatGPT stress-test → Lead with outcomes, not architecture. Nobody buys "multi-agent framework." They buy "AI workers that do your research while you sleep."

[2026-02-05] ChatGPT stress-test → Trading as lead example is a liability risk. Reposition as advanced example with disclaimers. Lead with general-purpose use cases (research, content, job hunting).

[2026-02-05] ChatGPT stress-test → API billing terrifies non-technical users. Must emphasize: hard caps, kill switches, pre-funded accounts, no surprise charges. Belt and suspenders.

[2026-02-05] ChatGPT stress-test → "open-corp" name reads as corporate/cold to non-technical users. Fine for v0.1 (builder audience), may need consumer-facing name later. Consider: name stays for framework, friendlier name for consumer product.

[2026-02-05] Grok validation → Gemini 2.0 Flash is NOT free on OpenRouter — it's metered (~$0.35/M input, $1.05/M output). Update all references. No models are truly free at scale on OpenRouter.

[2026-02-05] Grok validation → Claude Pro at $20/mo is correct, annual is $17/mo. Claude Code is included with Pro — no separate cost. This is a key selling point.

[2026-02-05] Grok validation → DeepSeek V3 is cheaper than initially assumed (~$0.14/M input, $0.28/M output). This is the workhorse model — route 80%+ of tasks here.

[2026-02-05] Grok validation → Competitive landscape exists (CrewAI, MetaGPT, AutoGPT, SuperAGI) but none target accessibility. Our moat is: easy setup + strict budget controls + multi-AI advisor pattern + open source.

[2026-02-05] Architecture simplification → Removed CEO agent abstraction. The project IS the corporation. Claude Code (or any LLM) IS the interface. No middleman. The Accountant remains as infrastructure (hard guardrail), not an agent. Simpler mental model, fewer hops, same power.

[2026-02-05] Architecture simplification → Model flexibility is a feature, not a limitation. User can swap Claude for Kimi 2.5, DeepSeek, or whatever fits their budget via OpenRouter. The framework doesn't care which LLM runs it.

[2026-02-05] Grok re-validation → Model availability fluctuates. Gemini 2.0 Flash and DeepSeek V3 may not be available under those exact names on OpenRouter. Implement graceful fallback in router.py. Use model-agnostic language in docs — specify tiers (cheap/mid/premium) not specific model names that may change.

[2026-02-05] Grok re-validation → Competitive landscape confirmed: CrewAI, MetaGPT, AutoGPT, SuperAGI all exist but none match our combo of terminal accessibility + hard budget guardrails + multi-AI advisors + model flexibility. CrewAI and AutoGPT are closest on accessibility but lack cost safety nets.

[2026-02-05] v0.1 implementation → Don't reference dataclass instances to get field defaults (e.g. `BudgetConfig().thresholds` fails if there are required fields). Use inline default dicts instead.
