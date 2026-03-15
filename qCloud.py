#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯云 DNSPod API 封装（无 SDK 版本）
基于 requests 直接调用腾讯云 API v3
"""

import json
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from urllib.parse import quote

import requests


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
        k_signing = hmac.new(k_service, b'tc3_request', hashlib.sha256).digest()
        return k_signing

    def sign(self, action: str, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        生成请求头

        Args:
            action: API 动作名称
            payload: 请求参数

        Returns:
            包含所有必要请求头的字典
        """
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

        # 步骤 1：规范请求
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

        # 步骤 2：创建待签名字符串
        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{self.service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"

        # 步骤 3：计算签名
        secret_key = self._get_signature_key(self.secret_key, date, self.service)
        signature = hmac.new(secret_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

        # 步骤 4：构造 Authorization 头
        authorization = (
            f"{algorithm} "
            f"Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        headers = {
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": self.host,
            "X-TC-Action": action,
            "X-TC-Version": self.version,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": self.region,
        }

        return headers


class QcloudApiv3:
    """腾讯云 DNSPod API v3 客户端封装（无 SDK 版本）"""

    def __init__(self, secret_id: str, secret_key: str):
        """
        初始化客户端

        Args:
            secret_id: 腾讯云 API SecretId
            secret_key: 腾讯云 API SecretKey
        """
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.signer = TencentCloudSigner(secret_id, secret_key)
        self.base_url = "https://dnspod.tencentcloudapi.com"
        self.session = requests.Session()

    def _call_api(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用腾讯云 API

        Args:
            action: API 动作名称
            payload: 请求参数

        Returns:
            API 响应字典
        """
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
                    "Error": {
                        "Code": "RequestError",
                        "Message": str(e)
                    },
                    "RequestId": ""
                }
            }

    def del_record(self, domain: str, record_id: int) -> Dict[str, Any]:
        """
        删除 DNS 记录

        Args:
            domain: 域名
            record_id: 记录 ID

        Returns:
            API 响应字典
        """
        payload = {
            "Domain": domain,
            "RecordId": record_id
        }

        resp = self._call_api("DeleteRecord", payload)
        response = resp.get("Response", {})

        if "Error" in response:
            return {
                "code": -1,
                "message": response["Error"].get("Message", "Unknown error")
            }

        return {
            "code": 0,
            "message": "None"
        }

    def _format_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化记录，将 RecordId 转为小写 id

        Args:
            record: 原始记录字典

        Returns:
            格式化后的记录字典
        """
        new_record = {}
        record["id"] = record.get('RecordId')
        for key in record:
            new_record[key.lower()] = record[key]
        return new_record

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> Dict[str, Any]:
        """
        获取 DNS 记录列表

        Args:
            domain: 域名
            length: 返回记录数量限制
            sub_domain: 子域名
            record_type: 记录类型 (A, CNAME, MX 等)

        Returns:
            包含记录列表的响应字典
        """
        payload = {
            "Domain": domain,
            "Subdomain": sub_domain,
            "RecordType": record_type,
            "Limit": length
        }

        resp = self._call_api("DescribeRecordList", payload)
        response = resp.get("Response", {})

        temp_resp = {
            "code": 0,
            "data": {
                "records": [],
                "domain": {}
            }
        }

        if "Error" in response:
            # 构造空响应
            domain_info = self.get_domain(domain)
            temp_resp["data"]["domain"]["grade"] = domain_info.get("DomainInfo", {}).get("Grade", "")
            return temp_resp

        for record in response.get('RecordList', []):
            temp_resp["data"]["records"].append(self._format_record(record))

        domain_info = self.get_domain(domain)
        temp_resp["data"]["domain"]["grade"] = domain_info.get("DomainInfo", {}).get("Grade", "")

        return temp_resp

    def create_record(
        self,
        domain: str,
        sub_domain: str,
        value: str,
        record_type: str = "A",
        line: str = "默认",
        ttl: int = 600
    ) -> Dict[str, Any]:
        """
        创建 DNS 记录

        Args:
            domain: 域名
            sub_domain: 子域名
            value: 记录值 (IP 地址或域名)
            record_type: 记录类型，默认 A
            line: 线路，默认 "默认"
            ttl: TTL 时间，默认 600 秒

        Returns:
            API 响应字典
        """
        payload = {
            "Domain": domain,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
            "TTL": ttl
        }

        resp = self._call_api("CreateRecord", payload)
        response = resp.get("Response", {})

        if "Error" in response:
            return {
                "code": -1,
                "message": response["Error"].get("Message", "Unknown error")
            }

        return {
            "code": 0,
            "message": "None"
        }

    def change_record(
        self,
        domain: str,
        record_id: int,
        sub_domain: str,
        value: str,
        record_type: str = "A",
        line: str = "默认",
        ttl: int = 600
    ) -> Dict[str, Any]:
        """
        修改 DNS 记录

        Args:
            domain: 域名
            record_id: 记录 ID
            sub_domain: 子域名
            value: 新的记录值
            record_type: 记录类型，默认 A
            line: 线路，默认 "默认"
            ttl: TTL 时间，默认 600 秒

        Returns:
            API 响应字典
        """
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
            return {
                "code": -1,
                "message": response["Error"].get("Message", "Unknown error")
            }

        return {
            "code": 0,
            "message": "None"
        }

    def get_domain(self, domain: str) -> Dict[str, Any]:
        """
        获取域名信息

        Args:
            domain: 域名

        Returns:
            域名信息字典
        """
        payload = {"Domain": domain}

        resp = self._call_api("DescribeDomain", payload)
        response = resp.get("Response", {})

        return response


if __name__ == "__main__":
    # 简单测试
    import os

    secret_id = os.environ.get("SECRETID", "")
    secret_key = os.environ.get("SECRETKEY", "")

    if secret_id and secret_key:
        client = QcloudApiv3(secret_id, secret_key)
        # 测试获取域名信息
        result = client.get_domain("example.com")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("请设置 SECRETID 和 SECRETKEY 环境变量")
