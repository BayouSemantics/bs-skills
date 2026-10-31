# Worktrees

- put worktrees in a git-ignored `.worktrees/` dir at repo root

## Worktree cleanup

If the worktree contains run data / assets / large files inside ignored dirs,
discuss with the user a migration plan (move to repo root or delete). Check `.gitignore`
for suitable dirs that already exist for such assets and propose that location if suitable.
