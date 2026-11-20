#!/usr/bin/env bash
set -euo pipefail

# Workflow concurrency serializes automation; users can still push during a run.
for attempt in 1 2 3; do
  # Usually main has not moved, so no additional download is needed.
  if git push origin HEAD:refs/heads/main; then
    exit 0
  fi

  if [ "$attempt" -eq 3 ]; then
    break
  fi

  git fetch --no-tags --depth=50 origin +refs/heads/main:refs/remotes/origin/main
  for deepen_attempt in 1 2 3; do
    if git merge-base HEAD origin/main >/dev/null; then
      break
    fi
    if [ "$(git rev-parse --is-shallow-repository)" != true ]; then
      break
    fi
    git fetch --no-tags --deepen=100 origin +refs/heads/main:refs/remotes/origin/main
  done
  if ! git merge-base HEAD origin/main >/dev/null; then
    echo "::error::No common ancestor in fetched history. Rerun from the latest main."
    exit 1
  fi
  if ! git rebase origin/main; then
    git rebase --abort
    echo "::error::Remote changes conflict with generated rules. Rerun the workflow to regenerate from the latest main."
    exit 1
  fi

  echo "Remote updates integrated; retrying push."
done

echo "::error::Could not push rule updates after 3 attempts."
exit 1
