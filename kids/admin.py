import argparse
import getpass
import os
import subprocess
import sys
import json
from control import Store

def main():
    parser = argparse.ArgumentParser(description="Root-only recovery and first-time PIN setup")
    parser.add_argument("action", choices=["set-pin", "initialize-stdin", "stop", "status"])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run this command with sudo from the parent's terminal.")
    if args.action == "initialize-stdin":
        from control import STATE
        if (STATE / "pin.json").exists():
            raise SystemExit("A parent PIN already exists; use the normal PIN-change flow.")
        data = sys.stdin.buffer.read(256)
        pin = json.loads(data)["pin"]
        Store().initialize(pin)
        subprocess.run(["systemctl", "restart", "omarchy-kids-control.service"], check=True)
    elif args.action == "set-pin":
        pin = getpass.getpass("New parent PIN (8–12 digits): ")
        if pin != getpass.getpass("Repeat PIN: "):
            raise SystemExit("PINs did not match.")
        Store().initialize(pin)
        subprocess.run(["systemctl", "restart", "omarchy-kids-control.service"], check=True)
        print("Parent PIN saved. Open Kids Controls from Omarchy's launcher.")
    elif args.action == "stop":
        from control import service_action
        service_action("disable-controls")
    else:
        subprocess.run(["systemctl", "status", "omarchy-kids-control.service", "omarchy-kids-policy.service"])

if __name__ == "__main__":
    main()
