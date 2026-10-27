---
name: skills-standard
description: Describes Agent skills standard. Use when writing a new skill.
metadata:
  author: Cody Kingham
  credit: Anthropic
---

# Skills Standard

Skills are folders of instructions, scripts, and resources that AI Agents load dynamically to improve performance
on specialized tasks. Agents choose to load skills for a given task based on its name and description.

## Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

Skills use a three-level loading system:

1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

## SKILLS.md format

The file consists of YAML frontmatter followed by markdown. The frontmatter keys are:

| Field | Required | Constraints / Description |
|---|---|---|
| `name` | Yes | Max 64 characters. Lowercase letters, numbers, and hyphens only. Must not start or end with a hyphen. |
| `description` | Yes | Max 1024 characters. Non-empty. Describes what the skill does and when to use it. |
| `metadata` | No | Arbitrary key-value mapping for additional metadata (a map from string keys to string values). |
| `disable-model-invocation` | No | Disables auto-loading by AI agents and makes the skill user-activated only. |

`description` value should follow the "[Does X]...use it when [doing Y]" formula and should be as concise as possible.

Use `disable-model-invocation` for user-activated skills when asked.

## Efficient Information Discovery

Skills should be optimized for efficient information discovery: write concise sentences which describe in plain
language the information. Utilize lists or diagrams to convey dense information / locations. Large skills involving
much content should use a router format with links to reference pages.

## Brevity and Clarity

Good skills are brief but clear. When editing skills, prefer delete and replace over append, if the new content has
topical overlap with existing material. Always consider how to simplify and consolidate without sacrificing clarity.
