cron { 'writes_per_process':   
   command => "/data/writes_per_process &",   
   user    => root,
   special => "reboot"
}

