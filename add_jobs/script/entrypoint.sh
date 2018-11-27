#!/bin/sh

ARGS=`env | awk -F '=' '{print $1}' | grep -e "^JOB_[0-9]*$"`

if [ ! -n "$ARGS" ];then
    rm -rf /var/spool/cron/crontabs/root
    for x in $ARGS
    do
        ARG=`eval echo '$'$x`
        echo "Add Cron Job : `echo $ARG | sed 's/#/\*/g'`"
        echo "$ARG > /proc/1/fd/1 2>/proc/1/fd/2 &" >> /var/spool/cron/crontabs/root
    done
    sed -i 's/#/\*/g' /var/spool/cron/crontabs/root
fi

echo "Cron Job List:"
crontab -l | egrep -v "run-parts|#|^$"

exec "$@"
