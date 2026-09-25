#!/usr/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $EUID != 0 ]]; then
  exec sudo /usr/bin/python3 -I "$root/packaging/setup.py" --user "$(id -un)" "$@"
fi
exec /usr/bin/python3 -I "$root/packaging/setup.py" "$@"
