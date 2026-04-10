
**Ansible Playbook: OCI QuickCache deployment**

- **Purpose**: Deploy the OCI QuickCache components (cleanup script, systemd service and timer, logrotate config) to a group of hosts.
- **Playbook**: [ansible/site.yml](ansible/site.yml)
- **Inventory**: [ansible/inventory.ini](ansible/inventory.ini) (edit to target your hosts)

**Prerequisites**
- Python and Ansible installed in a virtualenv/venv. Example activation used in this repo:

	source /config/venv/Ubuntu_24.04_x86_64/oci/bin/activate

**Run (example)**

```bash
cd ansible
ansible-playbook -i inventory.ini site.yml
```

Use `--check` for a dry run and `-vv` for verbose output.

**What the playbook does (summary)**
- Ensures a log directory exists on each host.
- Copies the cleanup Python script to the hosts (the script that runs `cleanup_cache`).
- Deploys a systemd unit and a systemd timer so cleanup runs periodically.
- Installs a logrotate configuration for the cache audit logs.
- Enables and starts the timer; reloads systemd when needed.

**Verify deployment**
- Check timer and service status on a host:

```bash
sudo systemctl status cleanup_cache.timer
sudo systemctl status cleanup_cache.service
```

- Follow service logs:

```bash
sudo journalctl -u cleanup_cache.service -f
```

**Notes and troubleshooting**
- Ansible may warn about interpreter discovery ("using the discovered Python interpreter at ..."). This is informational; ensure the target hosts have a suitable Python (3.8+ recommended).
- If you need to change the user the service runs as, edit the deployed unit in [ansible/roles/oci_qc/templates/cleanup_cache.service.j2] or adjust the role variables.
- To undo changes made by the playbook, consider running a cleanup play or manually removing the units and files from the hosts.

**Example play output** (typical run summary)

```
PLAY RECAP
densev4-2883 : ok=8 changed=6 unreachable=0 failed=0 skipped=0
densev4-4753 : ok=8 changed=6 unreachable=0 failed=0 skipped=0
```


