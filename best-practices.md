# Best Practices

## Keep CLAUDE.md Focused
- Root: project-level context only
- Module: specific to that code area
- Update when conventions change
- Don't repeat what's in package.json

## Use Skills for Reusable Workflows
- Bundle prompt + triggers + tools
- One skill per concern (review, test, etc.)
- Skills > commands for repeated tasks
- Version control your skills

## Use Hooks for Automation
- Pre-commit: type check + lint + test
- Post-edit: auto-format on save
- Never skip hooks (no --no-verify)
- Hooks catch issues before they ship

## Document Architecture Decisions
- ADR format in docs/decisions/
- Record the WHY, not just the WHAT
- Keep runbooks for ops procedures
- New team members read docs/ first

## Maintain Modular Structure
- Each src/ module = self-contained
- Module CLAUDE.md = focused context
- tools/ = shared scripts + prompts
- Clean separation of concerns
- Keep AI context minimal and precise

## Project Structure Reference

```
project/
├── CLAUDE.md                    # Project brain — overview, tech stack, conventions, commands
├── README.md                    # Standard readme for humans
├── docs/
│   ├── architecture.md          # High-level architecture overview
│   ├── decisions/               # ADRs (Architecture Decision Records)
│   └── runbooks/                # Ops procedures and playbooks
├── .claude/
│   ├── settings.json            # Permissions, model selection, hooks
│   ├── hooks/                   # Pre/post tool-use automation scripts
│   └── skills/                  # Reusable AI workflow definitions
│       ├── code-review/
│       │   └── SKILL.md
│       ├── refactor/
│       │   └── SKILL.md
│       └── release/
│           └── SKILL.md
├── tools/
│   ├── scripts/                 # Shared build/deploy scripts
│   └── prompts/                 # Reusable prompt templates
└── src/
    ├── api/
    │   └── CLAUDE.md            # Module-specific context for API layer
    ├── persistence/
    │   └── CLAUDE.md            # Module-specific context for data layer
    └── ...
```

## Settings Reference (.claude/settings.json)

```json
{
  "permissions": {
    "allow": [
      "Bash(npm run lint)",
      "Bash(npm run test *)",
      "Bash(npm run build)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git status)"
    ],
    "deny": [
      "Read(.env)",
      "Read(.env.*)",
      "Read(secrets/**)",
      "Bash(rm -rf *)",
      "Bash(git push --force *)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "./hooks/pre-commit.sh"
        }]
      }
    ]
  },
  "model": "claude-sonnet-4-6",
  "autoMemoryEnabled": true,
  "respectGitignore": true
}
```

## CLAUDE.md Template

```markdown
# CLAUDE.md — Project Brain

## Project Overview
A modular repository designed for building
Claude Code projects with structured AI context,
reusable skills, and automated workflows.

## Tech Stack
- [List your tech stack here]

## Key Components
- CLAUDE.md: Project memory and instructions
- .claude/skills: Reusable AI workflows
- .claude/hooks: Guardrails and automation
- docs/: Architecture decisions
- src/: Core application modules

## Conventions
- TypeScript strict, no `any` types
- Functional components + hooks only
- Dark mode first, light mode via overrides
- All API inputs validated with Zod
- Commit format: NM-XXX: [description]
- @phosphor-icons/react for all icons

## Commands
- npm run dev — start dev server
- npm run build — production build
- npm test — run Vitest suite
- npm run lint — ESLint check
- npx playwright test — e2e tests
```

## ADR Template (docs/decisions/)

```markdown
## ADR-001: [Title]
Status: Accepted
Date: YYYY-MM-DD

### Context
[Why this decision was needed]

### Decision
[What was decided]

### Consequences
- [Positive and negative impacts]
```

## Key Principles

1. **Context is king** — Give the AI (or any developer) just enough context to be effective, not more
2. **Automate quality gates** — Hooks and CI catch issues before they reach production
3. **Document decisions, not implementations** — Code shows WHAT, docs explain WHY
4. **Modular over monolithic** — Smaller, focused modules are easier to understand and maintain
5. **Skills over scripts** — Composable, reusable workflows beat one-off commands
6. **Deny by default** — Explicitly allow safe operations, deny destructive ones
7. **Version control everything** — Skills, hooks, prompts, and decisions belong in git
