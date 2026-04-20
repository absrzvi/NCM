cron { 'disk_mon':   
   command => "python /data/disk_mon.py",   
   user    => root,
   special => "reboot"
}

