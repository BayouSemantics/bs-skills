# Repo Setup

When creating a new repo:

- Set default branch to `master` (not `main`) unless asked otherwise.
- Add `.worktrees` to `.gitignore`

If a remote is set:

- use `gh` cli to configure branches to auto-delete after merge
- configure squash merge as default
- ask the user if they want to enable branch protections for `master`