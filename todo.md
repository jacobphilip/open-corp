# Task Tracker — open-corp

## In Progress

- [ ] Core framework: Accountant guardrail (wraps all API calls, enforces budget)
- [ ] Core framework: Worker base class
- [ ] Core framework: Model router with graceful fallback (if model unavailable, try next tier)
- [ ] Core framework: Project config loader (charter.yaml)
- [ ] Scripts: corp.py CLI (chat, hire, status)
- [ ] Trading example: ICT knowledge base integration
- [ ] Trading example: Caleb automated scanning
- [ ] Telegram integration: Same interface, different channel
- [ ] Non-trading template: Add researcher or content-repurposer as front-loaded value
- [ ] Docs: Review and update for simplified model
- [ ] Testing: Unit tests for Accountant guardrail
- [ ] Testing: Integration test for hire-from-template flow

## Done

- [x] Project scaffold and directory structure ✓ verified
- [x] README.md ✓ verified
- [x] CLAUDE.md (project configuration for LLM) ✓ verified
- [x] Charter template + trading example charter ✓ verified
- [x] Worker profiles (ICT, Caleb) ✓ verified
- [x] Documentation (Getting Started, Hiring Guide, Board Setup) ✓ verified
- [x] .env.example with all config options ✓ verified
- [x] .gitignore ✓ verified
- [x] requirements.txt ✓ verified
- [x] Simplified architecture: removed CEO agent abstraction ✓ verified
