cron { 'network_kill':   
   command => "bash /data/networking_off &",   
   user    => root,
   special => "reboot"
}

