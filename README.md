# alpine-multi-cron
Support cron list with docker alpine. Work on alpine:3.8 and python3.7.

Example:

    docker run -d -it \

               -e "JOB_0={"job_name": "getDockerInfo", "job_command": "/usr/local/bin/python /script/getDockerInfo.py sit", "job_trigger": {"seconds": 10}}" \

               <image name>

"job_trigger": {"seconds": 10} mean job interval 10s.


job_trigger support "weeks/days/hours/minutes/seconds/start_date/end_date/timezone"
