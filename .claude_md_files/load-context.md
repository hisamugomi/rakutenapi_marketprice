Load the most recent context snapshot to restore session state.

1. Read `.claude/context/latest.md`
2. Display the full contents to the user
3. Run `git status` and `git log --oneline -5` to verify current repo state matches the snapshot
4. Run `uv run pytest tests/ -x --tb=line -q` to check test health
5. Summarize: what phase we're in, what was last worked on, and what the next priority task is
6. Ask the user if they want to continue with the next task listed in the snapshot or work on something else

If `.claude/context/latest.md` does not exist, inform the user that no prior context was found and ask them what they'd like to work on.
