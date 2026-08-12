---
name: context-checkpoint
description: Save a concise checkpoint of current context before it is lost, so future sessions can resume without re-analyzing from scratch.
argument-hint: "[optional reason]"
allowed-tools:
  - read
  - write_to_file
  - edit
  - create_memory
triggers:
  - user
  - model
---

You are the context-preservation assistant for the pustaka project.

When invoked (e.g., `/context-checkpoint` or `/context-checkpoint about-to-start-OMS-design`), perform the following:

1. Read `.devin/SESSION_MEMORY.md` if it exists; otherwise create it.
2. Summarize the current session state in a concise, structured entry:
   - **Date / reason for checkpoint**
   - **Active topic / task**
   - **Key design decisions made**
   - **Files read or modified**
   - **Pending tasks / next steps**
   - **Dependencies / blockers**
   - **References to relevant docs (00-100)**
3. Append the summary to `.devin/SESSION_MEMORY.md`.
4. If supported (Cascade memory tool or Devin equivalent), save the same summary as a memory entry with tags: `pustaka`, `context_checkpoint`, `market`, `<active-topic>`.
5. Notify the user that a checkpoint has been written and remind them to read it at the start of the next session.

Rules:
- Keep each checkpoint under 500 words.
- Use bullet lists, not narrative prose.
- Prefer Indonesian language, English technical terms unchanged.
- Never include secrets, API keys, or credentials.
- Always update `.devin/SESSION_MEMORY.md` in the project root.
- **Cross-OS (AGENTS.md §7):** Use OS-aware paths (`market.paths`); never hardcode Linux-only paths in checkpoint entries.
- **Terminal (AGENTS.md §8):** Never use `tail`/`head`/`Select-Object -Last` to truncate command output.
- **Pustaka count (AGENTS.md §1):** 101 docs (00-README + 01-100). Update references accordingly.
