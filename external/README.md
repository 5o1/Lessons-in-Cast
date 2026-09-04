# External projects

This directory contains third-party projects used as dependencies or
implementation references. They are tracked as Git submodules.

Clone the workspace and initialize all external projects with:

```bash
git clone --recurse-submodules <repository-url>
```

After an ordinary clone, or after the parent repository changes a pinned commit,
initialize and synchronize the worktrees with:

```bash
git submodule update --init --recursive
```

The parent repository pins each submodule commit. `external/sources.toml` records
project-specific roles and setup notes that do not belong in `.gitmodules`.

Keep each project's upstream license, version information, and source URL intact.
