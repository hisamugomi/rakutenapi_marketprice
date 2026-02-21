Give a quick status report on the project.

1. Read `.claude/context/latest.md` and show the "Current State" and "Next Steps" sections
2. Run `git status --short` to show uncommitted changes
3. Run `git log --oneline -3` to show recent commits
4. Run `uv run pytest tests/ -x --tb=line -q` to check test status
5. Check which scrapers exist in `src/scrapers/` and whether they have tests
6. Check if ML models exist in `models/` directory
7. Summarize everything in a compact status report
