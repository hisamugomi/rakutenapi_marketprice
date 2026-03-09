Check the latest GitHub Actions workflow runs and show any failures.

Steps:
1. Run: `gh run list --limit 5`
2. If any run failed, run: `gh run view --log-failed` on the most recent failed run
3. Summarize: which workflow, which step failed, and what the error was.
4. If all runs passed, say so clearly.
