#!/usr/bin/env python3
# -*- coding:utf-8 -*-

"""
1、获取环境变量中的Job列表及任务执行周期
2、循环加入调度器
3、启动调度器
"""


import os
import re
import json
import asyncio
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


def get_jobs():
    job_list = []
    env_list = os.environ
    job_regex = re.compile(r'\bJOB_[0-9]*\b')
    for el in env_list.keys():
        if job_regex.match(el) is not None:
            job_json = json.loads(env_list[el])
            job_list.append({
                "job_name": job_json['job_name'],
                "job_command": job_json['job_command'],
                "job_trigger": job_json['job_trigger']
            })
    return job_list


def build_job(job_command):
    run_command = os.popen(job_command).readlines()
    if run_command is not None:
        messages = [x.strip("\n") for x in run_command]
    else:
        messages = None
    print("{time} [{command}] {messages}".format(time=time.time(), command=job_command, messages=messages))


if __name__ == '__main__':
    scheduler = AsyncIOScheduler()
    jobs = get_jobs()
    for j in jobs:
        scheduler.add_job(func=build_job, args=[j['job_command']], name=j['job_name'],
                          misfire_grace_time=3600,
                          trigger=IntervalTrigger(
                              weeks=j['job_trigger'].get("weeks", 0),
                              days=j['job_trigger'].get("days", 0),
                              hours=j['job_trigger'].get("hours", 0),
                              minutes=j['job_trigger'].get("minutes", 0),
                              seconds=j['job_trigger'].get("seconds", 0),
                              start_date=j['job_trigger'].get("start_date", None),
                              end_date=j['job_trigger'].get("end_date", None),
                              timezone=j['job_trigger'].get("timezone", None)
                          ))
    pending_jobs = scheduler.get_jobs()
    print("Job_Num: {}, Job List:".format(len(pending_jobs)))
    for x in pending_jobs:
        print("Job_name:{}, Job_command:{}, job_trigger:{}".format(x.name, x.args, x.trigger))
    scheduler.start()
    print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(e)

