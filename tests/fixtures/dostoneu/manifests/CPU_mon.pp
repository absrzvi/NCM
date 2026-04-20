cron { 'CPU_mon':   
   command => "/data/CPU_mon &",   
   user    => root,
   special => "reboot"
}

