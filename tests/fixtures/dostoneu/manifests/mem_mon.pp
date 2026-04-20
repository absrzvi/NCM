cron { 'mem_mon':   
   command => "/data/mem_mon &",   
   user    => root,
   special => "reboot"
}

