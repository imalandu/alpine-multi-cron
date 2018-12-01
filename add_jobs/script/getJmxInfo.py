#!/usr/bin/env python3
# -*- coding:utf-8 -*-

"""
1、获取本机信息，IP地址和主机名
2、从本机docker API获取Container列表
3、从本机docker API获取Container Config Env，先甄别出带有“JAVA_OPTS”字段的应用，并记录其IP及Port
4、使用Container IP及Port访问Jmx API，获取Jmx数据
5、构造ES数据，推送到ES
"""

import aiohttp
import asyncio
import socket
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
                "Maximum_Heap": {
                    "type": "float"
                },
                "Heap_Used": {
                    "type": "float"
                },
                "Non-Heap": {
                    "type": "float"
                },
                "Threads": {
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
    # return [get_host_ip(), socket.gethostname()]
    return ["172.16.5.33", socket.gethostname()]


async def async_http(session, url, method, **kwargs):
    # noinspection PyBroadException
    try:
        if method == 'post':
            async with session.post(url, data=kwargs['data'], headers=kwargs['headers'], timeout=15) as resp:
                return [resp.status, await resp.json()]
        elif method == 'get':
            async with session.get(url, timeout=15) as resp:
                return [resp.status, await resp.text()]
        elif method == 'put':
            async with session.put(url, data=kwargs['data'], headers=kwargs['headers'], timeout=15) as resp:
                return [resp.status, await resp.json()]
        elif method == 'head':
            async with session.head(url, timeout=2) as resp:
                return [resp.status, None]
        else:
            return [405, None]
    except Exception as e:
        print(f"{time.time()} getJmxInfo Func async_http() Error Message: {e}")


async def get_cons_list(docker_prefix, session):
    url = f"{docker_prefix}/containers/json"
    cons_result = await async_http(session=session, url=url, method='get')
    if cons_result[0] // 100 == 2:
        for con in json.loads(cons_result[1]):
            cons_info.update({
                con['Id']: {}
            })


def utils(env_list):
    result = {}
    for item in env_list:
        key, value = item.split("=", 1)
        result.update({key: value})
    return result


async def get_cons_info(docker_prefix, con_id, session, host_info):
    url = f"{docker_prefix}/containers/{con_id}/json"
    con_info = await async_http(session=session, url=url, method='get')
    if con_info[0] // 100 == 2:
        con_env = utils(json.loads(con_info[1])['Config']['Env'])
        m_key = {"JAVA_OPTS", "MARATHON_APP_ID"}
        if set(m_key).issubset(list(con_env.keys())):
            cons_info[con_id].update({
                "jmx_prefix": f"http://{con_env['LIBPROCESS_IP']}:{con_env['PORT0']}",
                "service_name": con_env['MARATHON_APP_ID'],
                "host_port": f"{con_env['LIBPROCESS_IP']}_{con_env['PORT0']}",
                "host": host_info
            })
        else:
            del cons_info[con_id]


async def get_jmx_info(jmx_prefix, con_id, session):
    url = f"{jmx_prefix}/admin/metrics"
    jmx_info = await async_http(session=session, url=url, method='get')
    if jmx_info[0] // 100 == 2:
        jmx_info_json = json.loads(jmx_info[1])
        cons_info[con_id].update({
            "@timestamp": time.time() * 1000,
            "Maximum_Heap": int(format(float(jmx_info_json['heap']), '0.0f')),
            "Heap_Used": int(format(float(jmx_info_json['heap.used']), '0.0f')),
            "Non-Heap": int(format(float(jmx_info_json['nonheap']), '0.0f')),
            "Threads": int(format(float(jmx_info_json['threads']), '0.0f'))
        })
        del cons_info[con_id]['jmx_prefix']


async def push_data(env_name, session, raw_data):
    def _es_index_name():
        return f"service_jvm-{env_name}-{time.strftime('%Y.%m.%d', time.localtime())}"

    async def check_index_mapping():
        # 查看索引状态
        async def is_index():
            return await async_http(session=session, method='head', url=f"{ES_URL}/{_es_index_name()}")

        # 创建索引
        async def create_index():
            return await async_http(session=session, url=f"{ES_URL}/{_es_index_name()}",
                                    method='put', data=json.dumps(ES_MAPPING), headers=ELK_MAPPING_HEADERS)

        # noinspection PyBroadException
        try:
            index_status = await is_index()
            if index_status[0] // 100 != 2:
                return await create_index()
            else:
                return [index_status[0], "Index 'marathon' is already exists."]
        except Exception as e:
            print(f"{time.time()} getJmx {env_name} Func es_index() Error Message: {e}")

    def _init_es_data():
        if isinstance(raw_data, dict):
            result = ""
            es_header = '{"index": {"_index": ' + '"{}", '.format(_es_index_name()) + '"_type": "doc"}}\n'
            for i in raw_data.values():
                result = result + es_header + f'{json.dumps(i)}\n'
            return [len(raw_data), result]
        else:
            return [0, None]

    await check_index_mapping()
    write_data = _init_es_data()
    if write_data[0] > 0:
        run_push = await async_http(session=session, url=f'{ES_URL}/_bulk', method='post',
                                    data=write_data[1], headers=ELK_BULK_HEADERS)
        return [write_data[0], run_push]


async def run(env_name):
    host_info = get_hostname_ip()
    docker_prefix = f"http://{host_info[0]}:2375"
    async with aiohttp.ClientSession() as s:
        await asyncio.ensure_future(get_cons_list(docker_prefix=docker_prefix, session=s))
        await asyncio.wait([asyncio.ensure_future(get_cons_info(docker_prefix=docker_prefix,
                                                                con_id=x,
                                                                session=s,
                                                                host_info=host_info)) for x in cons_info.keys()])
        await asyncio.wait([asyncio.ensure_future(get_jmx_info(jmx_prefix=cons_info[con_id]['jmx_prefix'],
                                                               con_id=con_id,
                                                               session=s)) for con_id in cons_info.keys()])
        push_result = await asyncio.ensure_future(push_data(env_name=env_name, session=s, raw_data=cons_info))
    return push_result


if __name__ == '__main__':
    cons_info = {}
    if (len(sys.argv) - 1) != 1 or sys.argv[1] not in ["pro", "uat", "perf", "sit"]:
        print(f"{time.time()} getJmxInfo parameter Error.")
    else:
        # noinspection PyBroadException
        try:
            loop = asyncio.get_event_loop()
            task = asyncio.ensure_future(run(env_name="sit"))
            loop.run_until_complete(task)
            task_result = task.result()
            if task_result is not None:
                if task_result[1][0] // 100 == 2:
                    if task_result[1][1]['errors']:
                        print(f"{time.time()} getJmxInfo Push failed. [{task_result[0]}]")
                    else:
                        print(f"{time.time()} getJmxInfo Push success. [{task_result[0]}]")
                else:
                    print(f"{time.time()} getJmxInfo Push failed. [Http Error Code({task_result[1][0]})]")
            else:
                print(f"{time.time()} getJmxInfo No Data to Push.")
        except Exception as er:
            print(f"{time.time()} getJmxInfo Error {er}")

