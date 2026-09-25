"""Do not open the desktop after an enabled boot policy failed to apply."""
from pathlib import Path
import subprocess

def main():
    if Path('/etc/omarchy-kids/controlled-on').exists():
        subprocess.run(['/usr/bin/systemctl','is-active','--quiet','omarchy-kids-policy.service'],check=True)

if __name__=='__main__': main()
