#!/usr/bin/env bash
# The one list of protected paths. Sourced, never run: protect-paths.sh (Edit|Write|MultiEdit)
# and block-dangerous.sh (Bash) both read it, so a path protected from one tool is protected
# from the other. Until board 714 the list lived in protect-paths.sh alone and the Bash hook
# did not know it: `printf x > .claude/constitution.md` and `cat .env` reached the shell.
#
# Each entry is an extended regular expression matched against one path: the file an edit tool
# names, or one word of a shell command. A hook that cannot find this file refuses the call.

# ---------------------------------------------------------------------------
# Narrow allowlist, checked BEFORE the deny patterns.
#
# `\.env$` below is a secrets heuristic: it cannot tell a config file from a
# credentials file by name. That is the right default and it stays. But this
# template ships .claude/project.env as a COMMITTED, secret-free config file
# and docs/TEMPLATE-SETUP.md Step 2 instructs the operator to edit it — so the
# heuristic was blocking the setup path of the very template it protects.
#
# Scoped as tightly as possible: this exact filename, only directly inside a
# .claude/ directory. Any other *.env, including .claude/anything-else.env and
# project.env outside .claude/, is still denied.
#
# Rejected alternative: renaming to project.sh. It reads better, but every
# project already built from this template has a project.env that three hooks
# read by name, and a rename would silently stop those hooks configuring
# themselves. Silent breakage of downstream projects costs more than one
# audited exception here. If a secret is ever put in this file, that is a
# review failure, not a hook failure — the file is committed and visible.
# ---------------------------------------------------------------------------
ALLOWED_PATTERNS=(
  '(^|/)\.claude/project\.env$'
  # A lock git left behind by a killed process: it has no content, and removing it is how a
  # run nobody watches gets its repository back. Everything else under .git/ stays guarded.
  '(^|/)\.git/index\.lock$'
)

# Secrets: refused to an edit AND to a shell command that reads them.
# A directory or dotfile is written `(^|/)name`: an edit tool sends an absolute path, a shell
# command usually one relative to the project root, and `/name` alone let `.git/config` and
# `.npmrc` through (board 714, the first audit).
SECRET_PATTERNS=(
  '\.env$'
  '\.env\.'
  '(^|/)secrets/'
  '(^|/)\.ssh/'
  '(^|/)\.aws/'
  '(^|/)\.gnupg/'
  '(^|/)\.npmrc$'
  '(^|/)\.pypirc$'
  'id_rsa$'
  'id_rsa\.pub$'
  'id_ed25519$'
  'id_ed25519\.pub$'
  '\.pem$'
  '\.key$'
  '\.p12$'
  '\.pfx$'
  'credentials\.json$'
  'service-account.*\.json$'
  'gcloud-key\.json$'
  # The key of the second model, kept in the operator's directory (board 056). The directory is
  # guarded as a whole below (no writing); this file may not be read either. A directory of
  # secrets there is covered by the pattern for such directories above.
  '(^|/)engine-ops/simplifier-key\.sh$'
)

# Guarded: anyone may read them, nobody in a Claude session may write them.
GUARDED_PATTERNS=(
  # The guardrails themselves. Added 2026-08-27 alongside the owner-ratified
  # grant letting spawned sessions write under .claude/hooks, .claude/unattended
  # and .claude/architecture so an overnight run can repair the harness it runs
  # on. Widening what an agent may edit is exactly when the things that define
  # its limits need a second layer: the permission list is one mechanism, and a
  # settings.local.json edit could quietly re-widen it. These three stay out of
  # reach in both mechanisms. Propose changes in .engine/overseer/audit.md.
  '\.claude/constitution\.md$'
  '\.claude/settings\.json$'
  '\.claude/settings\.local\.json$'
  # The rules approved from lessons (board 054): CLAUDE.md imports the file, so every line of it
  # steers every conversation. A line lands there one way only — `lesson_queue.py promote`, run
  # outside a session on the owner's «так»; an agent's own edit or shell write is refused.
  '(^|/)\.engine/rules\.md$'
  # The operator's directory (board 056): the board's inbox, the runner's programs and its
  # journal. An answer "from the owner" is a file in that inbox, so an agent that could write
  # there could answer its own question. Reading it stays free.
  '(^|/)engine-ops(/|$)'
  # «The owner looked it over» (board 100): a task's number in tasks/.reviewed takes it off the
  # owner's review list, so the file is the owner's word like an answer in the inbox. It arrives
  # in the branch or through the inbox; a number written here in the ordinary way the runner removes
  # before its push (not one a session works to get past it: docs/engine-limits.md, «The same Linux user»).
  '(^|/)tasks/\.reviewed$'
  '(^|/)\.git/'
  '(^|/)migrations/.*\.py$'
  '(^|/)alembic/versions/.*\.py$'
  'alembic\.ini$'
  '(^|/)\.github/workflows/'
)

# Patterns to deny absolutely to an edit. Match against the full path.
PROTECTED_PATTERNS=("${GUARDED_PATTERNS[@]}" "${SECRET_PATTERNS[@]}")
