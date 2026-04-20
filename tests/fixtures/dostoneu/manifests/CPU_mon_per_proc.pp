cron { 'CPU_mon_per_proc':   
   command => "/data/CPU_mon_per_proc &",   
   user    => root,
   special => "reboot"
}

