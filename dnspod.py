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
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict, Any, List

import requests

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


class TencentCloudSigner:
    """腾讯云 API 签名类"""

    def __init__(self, secret_id: str, secret_key: str):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.service = "dnspod"
        self.host = "dnspod.tencentcloudapi.com"
        self.region = ""
        self.version = "2021-03-23"

    def _get_signature_key(self, key: str, date_stamp: str, service_name: str) -> bytes:
        """生成签名密钥"""
        k_date = hmac.new(f"TC3{key}".encode('utf-8'), date_stamp.encode('utf-8'), hashlib.sha256).digest()
        k_service = hmac.new(k_date, service_name.encode('utf-8'), hashlib.sha256).digest()
        return hmac.new(k_service, b'tc3_request', hashlib.sha256).digest()

    def sign(self, action: str, payload: Dict[str, Any]) -> Dict[str, str]:
        """生成请求头"""
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

        http_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""

        content_type = "application/json"
        payload_json = json.dumps(payload)
        payload_bytes = payload_json.encode('utf-8')
        hashed_payload = hashlib.sha256(payload_bytes).hexdigest()

        canonical_headers = f"content-type:{content_type}\nhost:{self.host}\nx-tc-action:{action.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"

        canonical_request = (
            f"{http_method}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_payload}"
        )

        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{self.service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"

        secret_key = self._get_signature_key(self.secret_key, date, self.service)
        signature = hmac.new(secret_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

        authorization = (
            f"{algorithm} "
            f"Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": self.host,
            "X-TC-Action": action,
            "X-TC-Version": self.version,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": self.region,
        }


class DnsPodClient:
    """腾讯云 DNSPod API 客户端"""

    def __init__(self, secret_id: str, secret_key: str):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.signer = TencentCloudSigner(secret_id, secret_key)
        self.base_url = "https://dnspod.tencentcloudapi.com"
        self.session = requests.Session()

    def _call_api(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """调用腾讯云 API"""
        headers = self.signer.sign(action, payload)
        try:
            response = self.session.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "Response": {
                    "Error": {"Code": "RequestError", "Message": str(e)},
                    "RequestId": ""
                }
            }

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> Dict[str, Any]:
        """获取 DNS 记录列表"""
        payload = {
            "Domain": domain,
            "Subdomain": sub_domain,
            "RecordType": record_type,
            "Limit": length
        }

        resp = self._call_api("DescribeRecordList", payload)
        response = resp.get("Response", {})

        result = {
            "code": 0,
            "data": {"records": [], "domain": {}}
        }

        if "Error" not in response:
            for record in response.get('RecordList', []):
                formatted = {k.lower(): v for k, v in record.items()}
                formatted["id"] = record.get('RecordId')
                result["data"]["records"].append(formatted)

        # 获取域名信息
        domain_info = self._call_api("DescribeDomain", {"Domain": domain})
        result["data"]["domain"]["grade"] = domain_info.get("Response", {}).get("DomainInfo", {}).get("Grade", "")
        return result

    def change_record(self, domain: str, record_id: int, sub_domain: str,
                      value: str, record_type: str = "A", line: str = "默认", ttl: int = 600) -> Dict[str, Any]:
        """修改 DNS 记录"""
        payload = {
            "Domain": domain,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
            "TTL": ttl,
            "RecordId": record_id
        }

        resp = self._call_api("ModifyRecord", payload)
        response = resp.get("Response", {})

        if "Error" in response:
            return {"code": -1, "message": response["Error"].get("Message", "Unknown error")}
        return {"code": 0, "message": "None"}


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


def build_info(client: DnsPodClient) -> List[Dict[str, Any]]:
    """
    构建 DNS 记录信息

    Args:
        client: DnsPodClient 实例

    Returns:
        记录信息列表，失败返回空列表
    """
    def_info = []
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    try:
        ret = client.get_record(DOMAIN, 100, SUB_DOMAIN, 'A')
        records = ret.get("data", {}).get("records", [])

        for record in records:
            if record.get("line") == "默认":
                def_info.append({"recordId": record.get("id"), "value": record.get("value")})

        print(f"build_info success: ---- Time: {current_time} ---- ip：{def_info}")
    except Exception as e:
        traceback.print_exc()
        print(f"build_info ERROR: ---- Time: {current_time} ---- MESSAGE: {e}")

    return def_info


def change_dns(client: DnsPodClient, record_id: int, cf_ip: str) -> str:
    """
    更新 DNS 记录

    Args:
        client: DnsPodClient 实例
        record_id: 记录 ID
        cf_ip: 新的 IP 地址

    Returns:
        操作结果字符串
    """
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    try:
        client.change_record(DOMAIN, record_id, SUB_DOMAIN, cf_ip, "A", "默认", 600)
        print(f"change_dns success: ---- Time: {current_time} ---- ip：{cf_ip}")
        return f"ip:{cf_ip} 解析 {SUB_DOMAIN}.{DOMAIN} 成功"
    except Exception as e:
        traceback.print_exc()
        print(f"change_dns ERROR: ---- Time: {current_time} ---- MESSAGE: {e}")
        return f"ip:{cf_ip} 解析 {SUB_DOMAIN}.{DOMAIN} 失败"


def pushplus(content: str):
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
    client = DnsPodClient(SECRETID, SECRETKEY)

    # 获取 DNS 记录
    info = build_info(client)
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
        dns = change_dns(client, info[index]["recordId"], ip_address)
        pushplus_content.append(dns)

    # 发送推送
    if pushplus_content:
        pushplus('\n'.join(pushplus_content))


if __name__ == '__main__':
    main()
