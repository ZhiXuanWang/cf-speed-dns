#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DNSPod DNS 更新器
获取优选 IP 并更新 DNSPod DNS 记录
"""

import time
import traceback
import os
import json

import requests

from qCloud import QcloudApiv3

# 域名和子域名
DOMAIN = os.environ.get('DOMAIN')
SUB_DOMAIN = os.environ.get('SUB_DOMAIN')

# API 密钥
SECRETID = os.environ.get("SECRETID")
SECRETKEY = os.environ.get("SECRETKEY")

# pushplus_token
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 30


def get_cf_speed_test_ip(timeout=10, max_retries=5):
    """
    获取 Cloudflare 优选 IP

    Args:
        timeout: 单次请求超时时间
        max_retries: 最大重试次数

    Returns:
        优选 IP 字符串，失败返回 None
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(
                'https://ip.164746.xyz/ipTop.html',
                timeout=timeout
            )
            if response.status_code == 200:
                return response.text
        except Exception as e:
            print(f"获取优选 IP 失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                traceback.print_exc()
    return None


def build_info(cloud):
    """
    构建 DNS 记录信息

    Args:
        cloud: QcloudApiv3 实例

    Returns:
        记录信息列表，失败返回空列表
    """
    def_info = []
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    try:
        ret = cloud.get_record(DOMAIN, 100, SUB_DOMAIN, 'A')
        records = ret.get("data", {}).get("records", [])

        for record in records:
            if record.get("line") == "默认":
                info = {"recordId": record.get("id"), "value": record.get("value")}
                def_info.append(info)

        print(f"build_info success: ---- Time: {current_time} ---- ip：{def_info}")
    except Exception as e:
        traceback.print_exc()
        print(f"build_info ERROR: ---- Time: {current_time} ---- MESSAGE: {e}")

    return def_info


def change_dns(cloud, record_id, cf_ip):
    """
    更新 DNS 记录

    Args:
        cloud: QcloudApiv3 实例
        record_id: 记录 ID
        cf_ip: 新的 IP 地址

    Returns:
        操作结果字符串
    """
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    try:
        cloud.change_record(DOMAIN, record_id, SUB_DOMAIN, cf_ip, "A", "默认", 600)
        print(f"change_dns success: ---- Time: {current_time} ---- ip：{cf_ip}")
        return f"ip:{cf_ip} 解析 {SUB_DOMAIN}.{DOMAIN} 成功"
    except Exception as e:
        traceback.print_exc()
        print(f"change_dns ERROR: ---- Time: {current_time} ---- MESSAGE: {e}")
        return f"ip:{cf_ip} 解析 {SUB_DOMAIN}.{DOMAIN} 失败"


def pushplus(content):
    """
    发送 PushPlus 消息推送

    Args:
        content: 消息内容
    """
    if not PUSHPLUS_TOKEN:
        print("PUSHPLUS_TOKEN 未设置，跳过消息推送")
        return

    url = 'http://www.pushplus.plus/send'
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": "IP优选DNSPOD推送",
        "content": content,
        "template": "markdown",
        "channel": "wechat"
    }

    try:
        body = json.dumps(data).encode(encoding='utf-8')
        headers = {'Content-Type': 'application/json'}
        requests.post(url, data=body, headers=headers, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        print(f"消息推送失败: {e}")


def main():
    """主函数"""
    # 检查必要的环境变量
    if not all([DOMAIN, SUB_DOMAIN, SECRETID, SECRETKEY]):
        print("错误: 缺少必要的环境变量 (DOMAIN, SUB_DOMAIN, SECRETID, SECRETKEY)")
        return

    # 初始化 DNSPod 客户端
    cloud = QcloudApiv3(SECRETID, SECRETKEY)

    # 获取 DNS 记录
    info = build_info(cloud)
    if not info:
        print(f"错误: 未找到 {SUB_DOMAIN}.{DOMAIN} 的 DNS 记录")
        return

    # 获取最新优选 IP
    ip_addresses_str = get_cf_speed_test_ip()
    if not ip_addresses_str:
        print("错误: 无法获取优选 IP")
        return

    ip_addresses = [ip.strip() for ip in ip_addresses_str.split(',') if ip.strip()]
    if not ip_addresses:
        print("错误: 未解析到有效 IP 地址")
        return

    # 检查记录数量是否足够
    if len(ip_addresses) > len(info):
        print(f"警告: IP 数量({len(ip_addresses)})超过 DNS 记录数量({len(info)})，只更新前 {len(info)} 个")
        ip_addresses = ip_addresses[:len(info)]

    # 更新 DNS 记录
    pushplus_content = []
    for index, ip_address in enumerate(ip_addresses):
        dns = change_dns(cloud, info[index]["recordId"], ip_address)
        pushplus_content.append(dns)

    # 发送推送
    if pushplus_content:
        pushplus('\n'.join(pushplus_content))


if __name__ == '__main__':
    main()
