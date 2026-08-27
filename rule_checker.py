"""
rule_checker.py  -  NetSage AI: deterministic rule checker

This is the "safety net" that runs independently of the AI. It does NOT use
any AI/LLM call - it's plain regex/string checks over the show-command text
in cases.csv, looking for the 6 common config mistakes called out in the
project brief:

    1. Duplicate IP addresses
    2. Wrong / mismatched subnet masks
    3. Gateway mismatch
    4. Interface (or AP/RADIUS) down
    5. Missing / misconfigured VLAN (access-vlan, trunk pruning, native VLAN)
    6. Missing routes

Usage:
    python3 rule_checker.py cases.csv

Each check is scoped to the category where it makes sense (e.g. the gateway
check only runs on "Gateway" cases). This keeps false positives down, same
as a real lint tool would do, but it also means the checker will legitimately
miss things outside its 6 rules (e.g. HSRP/FHRP problems, RADIUS auth logic).
That's expected - the checker is a first-pass filter, not a replacement for
the AI + human review step.
"""
import csv
import re
import sys


def check_duplicate_ip(row):
    text = row["show_output"]
    if re.search(r"DUPADDR|Duplicate address", text, re.IGNORECASE):
        m = re.search(r"Duplicate address ([\d.]+)", text)
        ip = m.group(1) if m else "unknown"
        return f"Duplicate IP detected on {ip}"
    return None


def check_wrong_mask(row):
    text = row["show_output"]
    masks = set(re.findall(r"\b(?:255\.){3}\d{1,3}\b", text))
    if len(masks) > 1:
        return f"Mismatched subnet masks found: {', '.join(sorted(masks))}"
    return None


def check_gateway_mismatch(row):
    if row["category"] != "Gateway":
        return None
    text = row["show_output"]
    gw = re.search(r"Default Gateway\.*:\s*([\d.]+)", text)
    rtr = re.search(r"(?:GigabitEthernet|FastEthernet)\S*\s+([\d.]+)\s+YES", text)
    if gw and rtr:
        gw_ip, rtr_ip = gw.group(1), rtr.group(1)
        if gw_ip != rtr_ip and gw_ip.rsplit(".", 1)[0] == rtr_ip.rsplit(".", 1)[0]:
            return f"Gateway mismatch: PC points to {gw_ip}, router interface is actually {rtr_ip}"
    return None


def check_interface_down(row):
    text = row["show_output"]
    if re.search(r"\b(down|disassociated)\b", text, re.IGNORECASE):
        return "Down/disassociated state detected in show output"
    return None


def check_vlan_config(row):
    if row["category"] != "VLAN":
        return None
    text = row["show_output"]
    topo = row["topology_note"]

    m_access = re.search(r"switchport access vlan (\d+)", text)
    m_expected = re.search(r"VLAN\s?(\d+)", topo)
    if m_access and m_expected and m_access.group(1) != m_expected.group(1):
        return (f"Access-VLAN mismatch: port set to VLAN {m_access.group(1)}, "
                f"expected VLAN {m_expected.group(1)}")

    if "Vlans allowed on trunk" in text and m_expected:
        allowed_line = re.findall(r"Vlans allowed on trunk\s*\n\S+\s+([\d,]+)", text)
        if allowed_line and m_expected.group(1) not in allowed_line[0].split(","):
            return f"Trunk pruning: VLAN {m_expected.group(1)} missing from allowed-VLAN list"

    if "NATIVE_VLAN_MISMATCH" in text:
        return "Native VLAN mismatch across trunk"

    return None


def check_missing_route(row):
    if row["category"] != "Routing":
        return None
    text = row["show_output"]
    topo = row["topology_note"]

    if re.search(r"not in table", text, re.IGNORECASE):
        return "Route lookup failed - network not in routing table"

    target = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b", topo)
    if target:
        cidr = target.group(1)
        network = cidr.split("/")[0]
        if not re.search(r"^[A-Z]\s+" + re.escape(network) + r"/", text, re.MULTILINE):
            return f"Expected route to {cidr} not found in routing table"
    return None


CHECKS = [
    ("duplicate_ip", check_duplicate_ip),
    ("wrong_mask", check_wrong_mask),
    ("gateway_mismatch", check_gateway_mismatch),
    ("interface_down", check_interface_down),
    ("vlan_config", check_vlan_config),
    ("missing_route", check_missing_route),
]


def run(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total_flags = 0
    print(f"NetSage AI - Rule Checker sample run over {csv_path}")
    print(f"Cases loaded: {len(rows)}")
    print("=" * 78)

    for row in rows:
        hits = []
        for name, fn in CHECKS:
            result = fn(row)
            if result:
                hits.append((name, result))

        if hits:
            total_flags += len(hits)
            print(f"[{row['case_id']}] {row['category']} - {len(hits)} flag(s)")
            for name, msg in hits:
                print(f"    - {name}: {msg}")
        else:
            print(f"[{row['case_id']}] {row['category']} - no deterministic rule fired "
                  f"(needs AI + human review)")

    print("=" * 78)
    flagged_cases = sum(1 for row in rows if any(fn(row) for _, fn in CHECKS))
    print(f"Cases with at least one deterministic flag: {flagged_cases}/{len(rows)}")
    print(f"Total individual flags raised: {total_flags}")
    print("\nNote: cases with no flag are NOT 'no problem' - it means this rule-based\n"
          "checker's 6 patterns don't cover that fault type (e.g. FHRP/HSRP state,\n"
          "RADIUS auth failures, DNS record content). Those rely on the AI diagnosis\n"
          "+ human review step instead. See README for the full list of known gaps.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "cases.csv"
    run(path)
