source /config/venv/Ubuntu_24.04_x86_64/oci/bin/activate
ansible-playbook -i inventory.ini site.yml


/mnt/localdisk/object_store/OCI_QC_Cache is the default for cache cleanup service!!!
Verify the Setup

Reload the daemon: sudo systemctl daemon-reload
Restart the timer: sudo systemctl restart oci-qc-cleanup.timer
Verify: systemctl list-timers oci_qc_cleanup.timer


You can test that the configuration is valid by running a dry run:
bash
sudo logrotate -d /etc/logrotate.d/ociqc
