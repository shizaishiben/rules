#!/usr/bin/env bash
set -euo pipefail

# Workflow concurrency serializes automation; users can still push during a run.
for attempt in 1 2 3; do
  git fetch origin main
  if ! git rebase origin/main; then
    git rebase --abort
    echo "::error::Remote changes conflict with generated rules. Rerun the workflow to regenerate from the latest main."
    exit 1
  fi

  if git push origin HEAD:refs/heads/main; then
    exit 0
  fi

  echo "Push attempt $attempt failed; checking for concurrent updates."
done

echo "::error::Could not push rule updates after 3 attempts."
exit 1
