#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import requests
from qCloud import QcloudApiv3
import traceback
import os
import json

# 域名和子域名
DOMAIN = os.environ['DOMAIN']
SUB_DOMAIN = os.environ['SUB_DOMAIN']

# API 密钥
SECRETID = os.environ["SECRETID"]
SECRETKEY = os.environ["SECRETKEY"]

# pushplus_token
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]


def get_cf_speed_test_ip(timeout=10, max_retries=5):
    for attempt in range(max_retries):
        try:
            # 发送 GET 请求，设置超时
            response = requests.get('https://ip.164746.xyz/ipTop.html', timeout=timeout)

            # 检查响应状态码
            if response.status_code == 200:
                return response.text
        except Exception as e:
            traceback.print_exc()
            print(f"get_cf_speed_test_ip Request failed (attempt {attempt + 1}/{max_retries}): {e}")
    # 如果所有尝试都失败，返回 None 或者抛出异常，根据需要进行处理
    return None


def build_info(cloud):
    try:
        ret = cloud.get_record(DOMAIN, 100, SUB_DOMAIN, 'A')
        def_info = []
        for record in ret["data"]["records"]:
            info = {"recordId": record["id"], "value": record["value"]}
            if record["line"] == "默认":
                def_info.append(info)
        print(f"build_info success: ---- Time: " + str(
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())) + " ---- ip：" + str(def_info))
        return def_info
    except Exception as e:
        traceback.print_exc()
        print(f"build_info ERROR: ---- Time: " + str(
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())) + " ---- MESSAGE: " + str(e))


def change_dns(cloud, record_id, cf_ip):
    try:
        cloud.change_record(DOMAIN, record_id, SUB_DOMAIN, cf_ip, "A", "默认", 600)
        print(f"change_dns success: ---- Time: " + str(
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())) + " ---- ip：" + str(cf_ip))
        return "ip:" + str(cf_ip) + "解析" + str(SUB_DOMAIN) + "." + str(DOMAIN) + "成功"

    except Exception as e:
        traceback.print_exc()
        print(f"change_dns ERROR: ---- Time: " + str(
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())) + " ---- MESSAGE: " + str(e))
        return "ip:" + str(cf_ip) + "解析" + str(SUB_DOMAIN) + "." + str(DOMAIN) + "失败"


def pushplus(content):
    url = 'http://www.pushplus.plus/send'
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": "IP优选DNSPOD推送",
        "content": content,
        "template": "markdown",
        "channel": "wechat"
    }
    body = json.dumps(data).encode(encoding='utf-8')
    headers = {'Content-Type': 'application/json'}
    requests.post(url, data=body, headers=headers)


if __name__ == '__main__':
    # 构造环境
    cloud = QcloudApiv3(SECRETID, SECRETKEY)

    # 获取DNS记录
    info = build_info(cloud)

    # 获取最新优选IP
    ip_addresses_str = get_cf_speed_test_ip()
    ip_addresses = ip_addresses_str.split(',')

    pushplus_content = []
    # 遍历 IP 地址列表
    for index, ip_address in enumerate(ip_addresses):
        # 执行 DNS 变更
        dns = change_dns(cloud, info[index]["recordId"], ip_address)
        pushplus_content.append(dns)

    pushplus('\n'.join(pushplus_content))
