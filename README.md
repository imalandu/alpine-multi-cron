# alpine-multi-cron
Support cron list with docker alpine

STDOUT ----> /proc/1/fd/1

STDERR ----> /proc/1/fd/2

Notes: Use # replace *

Example:

docker run -it -e "JOB_0="# # # # # echo "This is a test cron job0""" \\

               -e "JOB_1="# # # # # echo "This is a test cron job1""" \
               
               <image name>
