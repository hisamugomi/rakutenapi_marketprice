Save a context snapshot before clearing or switching tasks.

1. Create the directory `.claude/context/` and `.claude/context/history/` if they don't exist.
2. Generate a timestamp string in format YYYYMMDD_HHMMSS.
3. Write a context snapshot to `.claude/context/latest.md` following the exact format specified in CLAUDE.md under "Context Snapshot Format". Fill in every section based on what you know from this session.
4. Copy the same content to `.claude/context/history/{timestamp}.md` as an archive.
5. Confirm to the user what was saved and show a brief summary.

Be thorough — capture all decisions, modified files, current state, and next steps. This snapshot is what the next session will use to pick up where we left off.
