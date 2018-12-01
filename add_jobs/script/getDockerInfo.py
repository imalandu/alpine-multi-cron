#!/usr/bin/env python3
# -*- coding:utf-8 -*-

"""
1、判断container相关的索引是否存在，不存在则建立
2、获取本地IP地址和主机名
3、通过Docker API获取容器信息
"""

import socket
import asyncio
import aiohttp
import time
import json
import sys

ES_MAPPING = {
    "settings": {
        "index": {
            "sort.field": ["@timestamp"],
            "sort.order": ["desc"]
        }
    },
    "mappings": {
        "doc": {
            "properties": {
                "@timestamp": {
                    "type": "date"
                },
                "service_name": {
                    "type": "text",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },
                "host": {
                    "type": "text",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },
                "host_port": {
                    "type": "text",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },
                "cpu_limit": {
                    "type": "float"
                },
                "cpu_usage": {
                    "type": "float"
                },
                "per_cpu_usage": {
                    "type": "float"
                },
                "mem_limit": {
                    "type": "text",
                    "fields": {
                        "keyword": {
                            "type": "keyword",
                            "ignore_above": 256
                        }
                    }
                },
                "mem_usage": {
                    "type": "float"
                }
            }
        }
    }
}

ES_URL = "http://10.10.19.36:9200"
ELK_MAPPING_HEADERS = {'content-type': 'application/json'}
ELK_BULK_HEADERS = {'content-type': 'application/x-ndjson'}


def get_hostname_ip():
    def get_host_ip():
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sk.connect(('8.8.8.8', 80))
            ip = sk.getsockname()[0]
        finally:
            sk.close()
        return ip
    return [get_host_ip(), socket.gethostname()]


class GetDockerData(object):

    def __init__(self):
        self._host_info = get_hostname_ip()
        self._prefix = "http://{host_ip}:2375".format(host_ip=self._host_info[0])
        self._cons_info = {}

    @staticmethod
    def __utils(env_list):
        result = {}
        for item in env_list:
            key, value = item.split("=", 1)
            result.update({key: value})
        return result

    @staticmethod
    def __calculate_cons_cpu_usage(cpu_usage, pre_cpu_usage, sys_cpu_usage, pre_sys_cpu_usage, online_cpus):
        cpu_percent = 0.00
        cpu_delta = cpu_usage - pre_cpu_usage
        sys_cpu_delta = sys_cpu_usage - pre_sys_cpu_usage
        if cpu_delta > 0 and sys_cpu_delta > 0:
            cpu_percent = (float(cpu_delta) / float(sys_cpu_delta)) * float(online_cpus) * 100.0
        return float(format(cpu_percent, '0.2f'))

    @staticmethod
    def __calculate_cons_mem_usage(mem_usage, mem_limit):
        mem_percent = 0.00
        if mem_usage > 0 and mem_limit > 0:
            mem_percent = (mem_usage / mem_limit) * 100.0
        return float(format(mem_percent, '0.2f'))

    @staticmethod
    async def __http_client(url, session):
        async with session.get(url, timeout=10) as resp:
            return [resp.status, await resp.json()]

    async def get_cons(self, session):
        url = "{prefix}/containers/json".format(prefix=self._prefix)
        cons_id = []
        cons_result = await self.__http_client(url, session)
        if cons_result[0] // 100 == 2:
            for con in cons_result[1]:
                cons_id.append(con['Id'])
                self._cons_info.update({
                    con['Id']: {}
                })
        return cons_id

    async def get_con_info(self, con_id, session):
        def trans_byte_cpu(byte):
            if float(byte) < 1:
                return float(byte)
            else:
                if "{}".format(int(float(byte))) == "{}".format(byte):
                    return int(float(byte))
                else:
                    return float(byte)

        def trans_byte_mem(byte):
            if float(byte) >= 1024:
                if float(byte) % 1024 == 0:
                    return "{}GB".format(format(float(byte) / 1024, '0.0f'))
                else:
                    return "{}GB".format(format(float(byte) / 1024, '0.1f'))
            else:
                return "{}MB".format(format(float(byte), '0.0f'))

        def get_env(con_env_info):
            env_list = self.__utils(con_env_info['Config']['Env'])
            if "MARATHON_APP_ID" in env_list:
                sn = env_list['MARATHON_APP_ID']
            else:
                sn = env_list['MESOS_CONTAINER_NAME']
            if "PORT0" in env_list:
                hp = env_list['LIBPROCESS_IP'] + "_" + env_list['PORT0']
            else:
                hp = env_list['LIBPROCESS_IP'] + "_" + "None"
            if "MARATHON_APP_RESOURCE_CPUS" in env_list:
                cl = env_list['MARATHON_APP_RESOURCE_CPUS']
            else:
                cl = con_env_info['HostConfig']['CpuShares'] / 1024
            if "MARATHON_APP_RESOURCE_MEM" in env_list:
                ml = env_list['MARATHON_APP_RESOURCE_MEM']
            else:
                ml = con_env_info['HostConfig']['Memory'] / 1024 / 1024
            return sn, hp, cl, ml

        url = "{prefix}/containers/{con_id}/json".format(prefix=self._prefix, con_id=con_id)
        con_info = await self.__http_client(url, session)
        if con_info[0] // 100 == 2:
            service_name, host_port, cpu_limit, mem_limit = get_env(con_info[1])
            self._cons_info[con_id].update({
                "service_name": service_name,
                "host_port": host_port,
                "cpu_limit": trans_byte_cpu(cpu_limit),
                "mem_limit": trans_byte_mem(mem_limit),
                "host": self._host_info
            })

    async def get_con_stats(self, con_id, session):
        url = "{prefix}/containers/{con_id}/stats?stream=0".format(prefix=self._prefix, con_id=con_id)
        con_stats = await self.__http_client(url, session)
        if con_stats[0] // 100 == 2:
            cpu_usage = con_stats[1]['cpu_stats']['cpu_usage']['total_usage']
            pre_cpu_usage = con_stats[1]['precpu_stats']['cpu_usage']['total_usage']
            sys_cpu_usage = con_stats[1]['cpu_stats']['system_cpu_usage']
            pre_sys_cpu_usage = con_stats[1]['precpu_stats']['system_cpu_usage']
            online_cpus = con_stats[1]['cpu_stats']['online_cpus']
            mem_usage = con_stats[1]['memory_stats']['usage']
            mem_limit = con_stats[1]['memory_stats']['limit']
            self._cons_info[con_id].update({
                "@timestamp": time.time() * 1000,
                "cpu_usage": self.__calculate_cons_cpu_usage(cpu_usage, pre_cpu_usage, sys_cpu_usage,
                                                             pre_sys_cpu_usage, online_cpus),
                "mem_usage": self.__calculate_cons_mem_usage(mem_usage, mem_limit)
            })

    async def run(self):
        if self._host_info[0] is not None:
            async with aiohttp.ClientSession() as session:
                cons_list = await asyncio.ensure_future(self.get_cons(session))
                cons_info = [asyncio.ensure_future(self.get_con_info(x, session)) for x in cons_list]
                cons_stats = [asyncio.ensure_future(self.get_con_stats(x, session)) for x in cons_list]
                await asyncio.wait(cons_info + cons_stats)
            for con_id in self._cons_info.keys():
                per_cpu_usage = self._cons_info[con_id]['cpu_usage'] / float(self._cons_info[con_id]['cpu_limit'])
                self._cons_info[con_id].update({
                    "per_cpu_usage": float(format(per_cpu_usage, '0.2f'))
                })
            return self._cons_info
        else:
            return None


class PushEsData(object):

    def __init__(self, env_name, containers_stats):
        self._env_name = env_name
        self._containers_stats = containers_stats

    def _es_index_name(self):
        es_index_name = "container-" + "{}-".format(self._env_name) + time.strftime("%Y.%m.%d", time.localtime())
        return es_index_name

    # aiohttp http客户端方法合集
    @staticmethod
    async def _async_http(session, url, method, **kwargs):
        try:
            if method == 'post':
                async with session.post(url, data=kwargs['data'], headers=kwargs['headers'], timeout=10) as resp:
                    return [resp.status, await resp.json()]
            elif method == 'put':
                async with session.put(url, data=kwargs['data'], headers=kwargs['headers'], timeout=10) as resp:
                    return [resp.status, await resp.json()]
            elif method == 'head':
                async with session.head(url, timeout=5) as resp:
                    return [resp.status, None]
            else:
                return [405, None]
        except Exception as e:
            print("{} getDockerInfo Func async_http() Error Message: {}".format(time.time(), e))

    # 如果没有索引则创建，如果有则pass
    async def check_index_mapping(self, session):
        # 查看索引状态
        async def is_index():
            return await self._async_http(session=session,
                                          url='{}/{}'.format(ES_URL, self._es_index_name()),
                                          method='head')

        # 创建索引
        async def create_index():
            return await self._async_http(session=session,
                                          url='{}/{}'.format(ES_URL, self._es_index_name()),
                                          method='put',
                                          data=json.dumps(ES_MAPPING),
                                          headers=ELK_MAPPING_HEADERS)
        try:
            index_status = await is_index()
            if index_status[0] // 100 != 2:
                return await create_index()
            else:
                return [index_status[0], "Index 'marathon' is already exists."]
        except Exception as e:
            print("{} getDockerInfo {} Func es_index() Error Message: {}".format(time.time(), self._env_name, e))

    def _init_es_data(self):
        if isinstance(self._containers_stats, dict):
            result = ""
            es_header = '{"index": {"_index": ' + '"{}", '.format(self._es_index_name()) + '"_type": "doc"}}\n'
            for i in self._containers_stats.values():
                result = result + es_header + '{}\n'.format(json.dumps(i))
            return [len(self._containers_stats.values()), result]
        else:
            return [0, None]

    async def push(self, session):
        write_data = self._init_es_data()
        if write_data[0] > 0:
            run_push = await self._async_http(session=session,
                                              url='{}/_bulk'.format(ES_URL),
                                              method='post',
                                              data=write_data[1],
                                              headers=ELK_BULK_HEADERS)
            return [write_data[0], run_push]

    async def run(self):
        async with aiohttp.ClientSession() as session:
            await self.check_index_mapping(session)
            result = await self.push(session)
        return result


async def main(env_name):
    get_data = GetDockerData()
    containers_stats = await get_data.run()
    if containers_stats is not None:
        push_data = PushEsData(env_name=env_name, containers_stats=containers_stats)
        push_result = await push_data.run()
        return push_result


if __name__ == '__main__':
    if (len(sys.argv) - 1) != 1 or sys.argv[1] not in ["pro", "uat", "perf", "sit"]:
        print("{} getDockerInfo parameter Error.".format(time.time()))
    else:
        try:
            loop = asyncio.get_event_loop()
            task = asyncio.ensure_future(main(env_name=sys.argv[1]))
            loop.run_until_complete(task)
            task_result = task.result()
            if task_result is not None:
                if task_result[1][0] // 100 == 2:
                    if task_result[1][1]['errors']:
                        print("{} getDockerInfo Push failed. [{}]".format(time.time(), task_result[0]))
                        pass
                    else:
                        print("{} getDockerInfo Push success. [{}]".format(time.time(), task_result[0]))
                else:
                    print("{} getDockerInfo Push failed. [Http Error Code({})]".format(time.time(), task_result[1][0]))
            else:
                print("{} getDockerInfo No Data to Push.".format(time.time()))
        except Exception as ex:
            print("{} getDockerInfo {}".format(time.time(), ex))

