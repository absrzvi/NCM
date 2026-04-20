cron { 'write_mon_total':   
   command => "/data/write_monitor_total &",   
   user    => root,
   special => "reboot"
}

