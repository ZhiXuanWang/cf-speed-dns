#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cloudflare DNS updater

Fetch preferred Cloudflare IPv4 addresses and update matching
Cloudflare A records safely.
"""

import ipaddress
import json
import os
import re
import sys
import time
import traceback
from typing import Dict, List

import requests


# =========================================================
# Configuration
# =========================================================

CF_API_TOKEN = (os.environ.get("CF_API_TOKEN") or "").strip()
CF_ZONE_ID = (os.environ.get("CF_ZONE_ID") or "").strip()
CF_DNS_NAME = (os.environ.get("CF_DNS_NAME") or "").strip().rstrip(".")
PUSHPLUS_TOKEN = (os.environ.get("PUSHPLUS_TOKEN") or "").strip()

IP_SOURCE_URL = (
    os.environ.get(
        "IP_SOURCE_URL",
        "https://ip.164746.xyz/ipTop.html"
    )
    or ""
).strip()

DEFAULT_TIMEOUT = 30


# =========================================================
# HTTP session
# =========================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": "cf-dns-updater/1.1"
})

CF_HEADERS = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json",
}


# =========================================================
# IP parsing
# =========================================================

def parse_ipv4_addresses(text: str) -> List[str]:
    """
    Extract valid unique IPv4 addresses from arbitrary response text.

    Supports:
        1.1.1.1
        1.1.1.1,2.2.2.2
        1.1.1.1\\n2.2.2.2
        HTML containing IP addresses
    """

    candidates = re.findall(
        r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])",
        text or ""
    )

    ips = []
    seen = set()

    for candidate in candidates:
        try:
            ip = str(ipaddress.IPv4Address(candidate))
        except ipaddress.AddressValueError:
            continue

        if ip not in seen:
            seen.add(ip)
            ips.append(ip)

    return ips


# =========================================================
# Preferred IP
# =========================================================

def get_cf_speed_test_ips(
    timeout: int = 10,
    max_retries: int = 5
) -> List[str]:

    for attempt in range(1, max_retries + 1):

        try:

            response = SESSION.get(
                IP_SOURCE_URL,
                timeout=timeout
            )

            response.raise_for_status()

            ips = parse_ipv4_addresses(response.text)

            if ips:
                return ips

            print(
                f"IP source returned no valid IPv4 address "
                f"(attempt {attempt}/{max_retries})"
            )

        except requests.RequestException as exc:

            print(
                f"Failed to fetch preferred IP "
                f"(attempt {attempt}/{max_retries}): {exc}"
            )

            if attempt == max_retries:
                traceback.print_exc()

        # Exponential retry delay:
        # 1s, 2s, 4s, 8s...
        if attempt < max_retries:
            time.sleep(
                min(2 ** (attempt - 1), 8)
            )

    return []


# =========================================================
# Cloudflare errors
# =========================================================

def cloudflare_error_message(
    payload,
    fallback="Unknown Cloudflare API error"
) -> str:

    if not isinstance(payload, dict):
        return fallback

    errors = payload.get("errors") or []

    if isinstance(errors, list) and errors:

        messages = []

        for error in errors:

            if not isinstance(error, dict):
                continue

            code = error.get("code")
            message = error.get("message")

            if code is not None and message:
                messages.append(
                    f"[{code}] {message}"
                )

            elif message:
                messages.append(
                    str(message)
                )

        if messages:
            return "; ".join(messages)

    return fallback


# =========================================================
# Get Cloudflare DNS records
# =========================================================

def get_dns_records(
    name: str
) -> List[Dict[str, str]]:

    """
    Get every A record matching the hostname.

    Handles Cloudflare pagination.
    """

    url = (
        "https://api.cloudflare.com/client/v4/"
        f"zones/{CF_ZONE_ID}/dns_records"
    )

    records = []

    page = 1

    while True:

        params = {
            "type": "A",
            "name": name,
            "page": page,
            "per_page": 100,
        }

        try:

            response = SESSION.get(
                url,
                headers=CF_HEADERS,
                params=params,
                timeout=DEFAULT_TIMEOUT
            )

            try:
                payload = response.json()

            except ValueError:

                print(
                    "Cloudflare returned invalid JSON "
                    f"while listing DNS records: "
                    f"HTTP {response.status_code}"
                )

                print(
                    response.text[:1000]
                )

                return []

        except requests.RequestException as exc:

            print(
                f"Failed to get DNS records: {exc}"
            )

            traceback.print_exc()

            return []

        # Check BOTH HTTP status and Cloudflare success field.
        if not response.ok or not payload.get("success"):

            error = cloudflare_error_message(
                payload,
                (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
            )

            print(
                f"Failed to get DNS records: {error}"
            )

            return []

        result = payload.get("result") or []

        for record in result:

            if not isinstance(record, dict):
                continue

            record_name = str(
                record.get("name", "")
            ).rstrip(".")

            if (
                record.get("type") == "A"
                and record_name.lower() == name.lower()
                and record.get("id")
            ):

                records.append({
                    "id": str(record["id"]),
                    "content": str(
                        record.get("content", "")
                    ),
                })

        result_info = (
            payload.get("result_info")
            or {}
        )

        total_pages = int(
            result_info.get("total_pages")
            or 1
        )

        if page >= total_pages:
            break

        page += 1

    # Stable ordering between runs.
    records.sort(
        key=lambda item: item["id"]
    )

    return records


# =========================================================
# Build safe update plan
# =========================================================

def build_update_plan(
    records: List[Dict[str, str]],
    target_ips: List[str]
):

    """
    Prefer DNS records that already contain a desired IP.

    Example:

        DNS:
            1.1.1.1
            2.2.2.2

        Preferred IP list:
            2.2.2.2

    We should NOT unnecessarily change the first DNS record
    to 2.2.2.2.

    We simply recognize that 2.2.2.2 is already present.
    """

    remaining_records = list(records)

    plan = []

    unmatched_ips = []

    # First find IPs that are already configured.
    for ip in target_ips:

        match_index = next(
            (
                index
                for index, record
                in enumerate(remaining_records)
                if record.get("content") == ip
            ),
            None
        )

        if match_index is None:

            unmatched_ips.append(ip)

        else:

            record = remaining_records.pop(
                match_index
            )

            plan.append(
                (record, ip)
            )

    # Assign missing IPs to remaining records.
    for record, ip in zip(
        remaining_records,
        unmatched_ips
    ):

        plan.append(
            (record, ip)
        )

    return plan


# =========================================================
# Update DNS
# =========================================================

def update_dns_record(
    record_info: Dict[str, str],
    name: str,
    cf_ip: str
) -> str:

    record_id = record_info["id"]

    current_ip = record_info.get(
        "content",
        ""
    )

    current_time = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime()
    )

    # Already correct
    if current_ip == cf_ip:

        print(
            "cf_dns_change skip: "
            f"---- Time: {current_time} ---- "
            f"ip: {cf_ip} "
            "(already current)"
        )

        return (
            f"ip:{cf_ip} -> {name}: "
            "skipped (already current)"
        )

    url = (
        "https://api.cloudflare.com/client/v4/"
        f"zones/{CF_ZONE_ID}/dns_records/{record_id}"
    )

    # IMPORTANT:
    #
    # PATCH changes only the field we specify.
    #
    # This preserves:
    # - proxied
    # - ttl
    # - comments
    # - tags
    # - settings
    # - other record properties
    #
    data = {
        "content": cf_ip
    }

    try:

        response = SESSION.patch(
            url,
            headers=CF_HEADERS,
            json=data,
            timeout=DEFAULT_TIMEOUT
        )

        try:
            payload = response.json()

        except ValueError:
            payload = {}

        current_time = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime()
        )

        if (
            response.ok
            and payload.get("success")
        ):

            print(
                "cf_dns_change success: "
                f"---- Time: {current_time} ---- "
                f"{current_ip or '<empty>'} -> {cf_ip}"
            )

            return (
                f"ip:{cf_ip} -> {name}: success"
            )

        error = cloudflare_error_message(
            payload,
            (
                f"HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        )

        print(
            "cf_dns_change ERROR: "
            f"---- Time: {current_time} ---- "
            f"MESSAGE: {error}"
        )

        return (
            f"ip:{cf_ip} -> {name}: "
            f"failed ({error})"
        )

    except requests.RequestException as exc:

        current_time = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime()
        )

        print(
            "cf_dns_change ERROR: "
            f"---- Time: {current_time} ---- "
            f"MESSAGE: {exc}"
        )

        traceback.print_exc()

        return (
            f"ip:{cf_ip} -> {name}: "
            f"failed ({exc})"
        )


# =========================================================
# PushPlus
# =========================================================

def push_plus(content: str) -> None:

    if not PUSHPLUS_TOKEN:

        print(
            "PUSHPLUS_TOKEN not set; "
            "skipping notification"
        )

        return

    url = "https://www.pushplus.plus/send"

    data = {
        "token": PUSHPLUS_TOKEN,
        "title": "IP优选DNSCF推送",
        "content": content,
        "template": "markdown",
        "channel": "wechat",
    }

    try:

        response = SESSION.post(
            url,
            json=data,
            timeout=DEFAULT_TIMEOUT
        )

        response.raise_for_status()

        try:

            payload = response.json()

            if (
                isinstance(payload, dict)
                and payload.get("code")
                not in (None, 200)
            ):

                print(
                    "PushPlus returned an error: "
                    + json.dumps(
                        payload,
                        ensure_ascii=False
                    )
                )

        except ValueError:
            pass

    except requests.RequestException as exc:

        # Notification failure must not break DNS job.
        print(
            f"Push notification failed: {exc}"
        )


# =========================================================
# Main
# =========================================================

def main() -> int:

    # -----------------------------------------------------
    # Check configuration
    # -----------------------------------------------------

    missing = [
        env_name
        for env_name, value in (
            (
                "CF_API_TOKEN",
                CF_API_TOKEN
            ),
            (
                "CF_ZONE_ID",
                CF_ZONE_ID
            ),
            (
                "CF_DNS_NAME",
                CF_DNS_NAME
            ),
        )
        if not value
    ]

    if missing:

        print(
            "Error: missing required "
            "environment variables: "
            + ", ".join(missing)
        )

        return 1

    # -----------------------------------------------------
    # Get preferred IPs
    # -----------------------------------------------------

    ip_addresses = get_cf_speed_test_ips()

    if not ip_addresses:

        print(
            "Error: unable to obtain a valid "
            "preferred IPv4 address"
        )

        return 1

    print(
        "Preferred IPs: "
        + ", ".join(ip_addresses)
    )

    # -----------------------------------------------------
    # Get existing Cloudflare records
    # -----------------------------------------------------

    dns_records = get_dns_records(
        CF_DNS_NAME
    )

    if not dns_records:

        print(
            f"Error: no A records found "
            f"for {CF_DNS_NAME}"
        )

        return 1

    print(
        f"Found {len(dns_records)} "
        "matching A record(s)"
    )

    # -----------------------------------------------------
    # Handle IP/record count mismatch
    # -----------------------------------------------------

    if len(ip_addresses) > len(dns_records):

        print(
            f"Warning: got {len(ip_addresses)} IPs "
            f"but only {len(dns_records)} A records; "
            f"only the first {len(dns_records)} "
            "IPs will be used"
        )

        ip_addresses = ip_addresses[
            :len(dns_records)
        ]

    elif len(ip_addresses) < len(dns_records):

        print(
            f"Warning: got only "
            f"{len(ip_addresses)} IP(s) "
            f"for {len(dns_records)} A records. "
            "Extra DNS records will be left unchanged."
        )

    # -----------------------------------------------------
    # Build update plan
    # -----------------------------------------------------

    update_plan = build_update_plan(
        dns_records,
        ip_addresses
    )

    results = []

    failed = False

    # -----------------------------------------------------
    # Apply updates
    # -----------------------------------------------------

    for record_info, ip_address in update_plan:

        result = update_dns_record(
            record_info,
            CF_DNS_NAME,
            ip_address
        )

        results.append(result)

        if "failed" in result:
            failed = True

    # -----------------------------------------------------
    # Push notification
    # -----------------------------------------------------

    if results:

        push_plus(
            "\n".join(results)
        )

    # cron/systemd can detect failure now.
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
