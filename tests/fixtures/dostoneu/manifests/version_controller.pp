cron { 'version_control':   
   command => "python3 /data/client.py &",   
   user    => root,
   special => "reboot"
}

