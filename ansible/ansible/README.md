source /config/venv/Ubuntu_24.04_x86_64/oci/bin/activate
ansible-playbook -i inventory.ini site.yml

PLAY [compute] **************************************************************************************************************************

TASK [Gathering Facts] ******************************************************************************************************************
[WARNING]: Host 'densev4-2883' is using the discovered Python interpreter at '/usr/bin/python3.12', but future installation of another Python interpreter could cause a different interpreter to be discovered. See https://docs.ansible.com/ansible-core/2.20/reference_appendices/interpreter_discovery.html for more information.
ok: [densev4-2883]
[WARNING]: Host 'densev4-4753' is using the discovered Python interpreter at '/usr/bin/python3.12', but future installation of another Python interpreter could cause a different interpreter to be discovered. See https://docs.ansible.com/ansible-core/2.20/reference_appendices/interpreter_discovery.html for more information.
ok: [densev4-4753]

TASK [oci_qc : Ensure log directory exists] *********************************************************************************************
changed: [densev4-2883]
changed: [densev4-4753]

TASK [oci_qc : Copy cleanup Python script] **********************************************************************************************
changed: [densev4-4753]
changed: [densev4-2883]

TASK [oci_qc : Deploy systemd service] **************************************************************************************************
changed: [densev4-4753]
changed: [densev4-2883]

TASK [oci_qc : Copy systemd timer] ******************************************************************************************************
changed: [densev4-2883]
changed: [densev4-4753]

TASK [oci_qc : Copy logrotate config] ***************************************************************************************************
changed: [densev4-2883]
changed: [densev4-4753]

TASK [oci_qc : Ensure timer is enabled and started] *************************************************************************************
changed: [densev4-2883]
changed: [densev4-4753]

RUNNING HANDLER [oci_qc : reload systemd] ***********************************************************************************************
ok: [densev4-4753]
ok: [densev4-2883]

PLAY RECAP ******************************************************************************************************************************
densev4-2883               : ok=8    changed=6    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
densev4-4753               : ok=8    changed=6    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0


Before cleanup:
ls -lR /object_store_densev4-2883/OCI_QC_Cache/|wc
   8274   73971  501177

The cleanup log:
2026-04-10 05:28:32,535 - INFO - Stats for /mnt/localdisk/object_store/OCI_QC_Cache: Disk usage: 9.79%, Total used inodes on disk: 25420
2026-04-10 05:28:32,568 - INFO - Triggered cleanup: size=1073741824, files=8192
2026-04-10 05:28:32,719 - INFO - Cleanup finished. Removed 7492 files, cleared 981991424 bytes.
2026-04-10 05:30:01,568 - INFO - Stats for /mnt/localdisk/object_store/OCI_QC_Cache: Disk usage: 9.78%, Total used inodes on disk: 17928
2026-04-10 06:00:01,570 - INFO - Stats for /mnt/localdisk/object_store/OCI_QC_Cache: Disk usage: 9.78%, Total used inodes on disk: 17928

After cleanup: - based on number of files (1000, experimental)
ls -lR /object_store_densev4-2883/OCI_QC_Cache/|wc
    782    6543   45270

To stop the cleanup:
sudo systemctl stop oci_qc_cleanup.timer

/mnt/localdisk/object_store/OCI_QC_Cache is the default for cache cleanup service!!!
Verify the Setup

Reload the daemon: sudo systemctl daemon-reload
Restart the timer: sudo systemctl restart oci-qc-cleanup.timer
Verify: systemctl list-timers oci_qc_cleanup.timer


You can test that the configuration is valid by running a dry run:
bash
sudo logrotate -d /etc/logrotate.d/ociqc
