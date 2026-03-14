#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯云 DNSPod API v3 封装
基于腾讯云 SDK 的 DNSPod 操作封装

参考文档: https://cloud.tencent.com/document/product/302/8517
"""

import json
from typing import Dict, Any, Optional

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.dnspod.v20210323 import dnspod_client, models


class QcloudApiv3:
    """腾讯云 DNSPod API v3 客户端封装"""

    def __init__(self, secret_id: str, secret_key: str):
        """
        初始化客户端

        Args:
            secret_id: 腾讯云 API SecretId
            secret_key: 腾讯云 API SecretKey
        """
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.cred = credential.Credential(secret_id, secret_key)

    def del_record(self, domain: str, record_id: int) -> Dict[str, Any]:
        """
        删除 DNS 记录

        Args:
            domain: 域名
            record_id: 记录 ID

        Returns:
            API 响应字典
        """
        client = dnspod_client.DnspodClient(self.cred, "")
        req_model = models.DeleteRecordRequest()
        params = {
            "Domain": domain,
            "RecordId": record_id
        }
        req_model.from_json_string(json.dumps(params))

        resp = client.DeleteRecord(req_model)
        resp = json.loads(resp.to_json_string())
        resp["code"] = 0
        resp["message"] = "None"
        return resp

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
        try:
            client = dnspod_client.DnspodClient(self.cred, "")

            req_model = models.DescribeRecordListRequest()
            params = {
                "Domain": domain,
                "Subdomain": sub_domain,
                "RecordType": record_type,
                "Limit": length
            }
            req_model.from_json_string(json.dumps(params))

            resp = client.DescribeRecordList(req_model)
            resp = json.loads(resp.to_json_string())

            temp_resp = {
                "code": 0,
                "data": {
                    "records": [],
                    "domain": {}
                }
            }

            for record in resp.get('RecordList', []):
                temp_resp["data"]["records"].append(self._format_record(record))

            temp_resp["data"]["domain"]["grade"] = self.get_domain(domain).get("DomainInfo", {}).get("Grade", "")
            return temp_resp

        except TencentCloudSDKException:
            # 构造空响应
            temp_resp = {
                "code": 0,
                "data": {
                    "records": [],
                    "domain": {
                        "grade": self.get_domain(domain).get("DomainInfo", {}).get("Grade", "")
                    }
                }
            }
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
        client = dnspod_client.DnspodClient(self.cred, "")
        req = models.CreateRecordRequest()
        params = {
            "Domain": domain,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
            "TTL": ttl
        }
        req.from_json_string(json.dumps(params))

        resp = client.CreateRecord(req)
        resp = json.loads(resp.to_json_string())
        resp["code"] = 0
        resp["message"] = "None"
        return resp

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
        client = dnspod_client.DnspodClient(self.cred, "")
        req = models.ModifyRecordRequest()
        params = {
            "Domain": domain,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
            "TTL": ttl,
            "RecordId": record_id
        }
        req.from_json_string(json.dumps(params))

        resp = client.ModifyRecord(req)
        resp = json.loads(resp.to_json_string())
        resp["code"] = 0
        resp["message"] = "None"
        return resp

    def get_domain(self, domain: str) -> Dict[str, Any]:
        """
        获取域名信息

        Args:
            domain: 域名

        Returns:
            域名信息字典
        """
        client = dnspod_client.DnspodClient(self.cred, "")
        req = models.DescribeDomainRequest()
        params = {"Domain": domain}
        req.from_json_string(json.dumps(params))

        resp = client.DescribeDomain(req)
        return json.loads(resp.to_json_string())
