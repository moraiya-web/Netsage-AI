"""
build_data.py
Generates the three core CSV deliverables for the NetSage AI project:
  - cases.csv            -> the 30-case troubleshooting dataset
  - ai_diagnosis_log.csv -> what the AI assistant said for every case
  - human_review_log.csv -> what the human reviewer decided (Accepted/Edited/Rejected)

Run once with: python3 build_data.py
"""
import csv

# ---------------------------------------------------------------------------
# 1. THE 30 CASES
# ---------------------------------------------------------------------------
cases = [

# ---------------- VLAN (4) ----------------
dict(case_id="C01", category="VLAN", severity="Medium", osi_layer="Layer 2",
 concept_tag="VLAN port assignment",
 symptom="PC1 and PC2 are both supposed to be in VLAN 10 on switch SW1, but PC2 (Fa0/3) cannot ping PC1 (Fa0/1) even though both ports show connected.",
 topology_note="Access switch SW1; PC1 on Fa0/1 in VLAN10, PC2 on Fa0/3 should also be VLAN10 but port config differs.",
 show_output="""SW1# show vlan brief

VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Fa0/2, Fa0/3, Fa0/4
10   Sales                            active    Fa0/1
20   Engineering                      active    Fa0/5, Fa0/6

SW1# show running-config interface fa0/3
interface FastEthernet0/3
 switchport mode access
 switchport access vlan 1""",
 expected_fault="Fa0/3 is still assigned to default VLAN1 instead of VLAN10 (switchport access vlan was never updated)."),

dict(case_id="C02", category="VLAN", severity="High", osi_layer="Layer 2",
 concept_tag="Trunk allowed-VLAN list",
 symptom="A PC plugged into Fa0/8 on SW2 (VLAN10) cannot reach any other VLAN10 host on SW1, even though the port is up/up.",
 topology_note="SW1-SW2 connected via trunk Gi0/1; PC in VLAN10 on SW2 needs Gi0/1 to carry VLAN10 traffic.",
 show_output="""SW1# show interfaces trunk

Port        Mode         Encapsulation  Status        Native vlan
Gi0/1       on           802.1q         trunking      1

Port        Vlans allowed on trunk
Gi0/1       1,20,30

Port        Vlans allowed and active in management domain
Gi0/1       1,20,30""",
 expected_fault="VLAN10 is not included in the trunk's allowed-VLAN list on Gi0/1, so VLAN10 frames get pruned at the trunk."),

dict(case_id="C03", category="VLAN", severity="High", osi_layer="Layer 3",
 concept_tag="SVI shutdown",
 symptom="PCs in VLAN30 get a valid DHCP IP but cannot ping their gateway 192.168.30.1.",
 topology_note="L3 switch with SVIs for VLAN10/20/30; VLAN30 is the newly added Guest VLAN.",
 show_output="""L3SW# show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
Vlan1                   unassigned      YES unset  up                    up
Vlan10                  192.168.10.1    YES manual up                    up
Vlan20                  192.168.20.1    YES manual up                    up
Vlan30                  192.168.30.1    YES manual administratively down down""",
 expected_fault="The VLAN30 SVI (interface Vlan30) is administratively shut down on the L3 switch."),

dict(case_id="C04", category="VLAN", severity="Medium", osi_layer="Layer 2",
 concept_tag="Native VLAN mismatch",
 symptom="Two VLAN10 PCs on different switches (SW1, SW2) cannot reach each other even though both have valid VLAN10 IPs.",
 topology_note="SW1 and SW2 connected via trunk Gi0/1; both switches carry VLAN10 for the same subnet.",
 show_output="""SW1# show interfaces gi0/1 trunk
Port        Mode         Encapsulation  Status        Native vlan
Gi0/1       on           802.1q         trunking      1

%CDP-4-NATIVE_VLAN_MISMATCH: Native VLAN mismatch discovered on GigabitEthernet0/1 (1), with SW2 GigabitEthernet0/1 (10).""",
 expected_fault="Native VLAN mismatch on the trunk (SW1=VLAN1, SW2=VLAN10) causes VLAN10 traffic to be tagged/handled incorrectly."),

# ---------------- Gateway (4) ----------------
dict(case_id="C05", category="Gateway", severity="High", osi_layer="Layer 3",
 concept_tag="Default gateway misconfiguration",
 symptom="PC1 (192.168.10.5) cannot reach anything outside its own subnet; ping to its configured gateway times out.",
 topology_note="R1 GigabitEthernet0/0 is the real gateway for VLAN10 (192.168.10.0/24).",
 show_output="""PC1> ipconfig
IP Address......................: 192.168.10.5
Subnet Mask......................: 255.255.255.0
Default Gateway..................: 192.168.10.254

R1# show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0      192.168.10.1    YES manual up                    up""",
 expected_fault="PC1 is configured with the wrong default gateway (192.168.10.254); the router's real interface IP is 192.168.10.1."),

dict(case_id="C06", category="Gateway", severity="Critical", osi_layer="Layer 1/2",
 concept_tag="Gateway interface down",
 symptom="All PCs in VLAN20 lost internet and inter-VLAN access at the same time.",
 topology_note="R1 GigabitEthernet0/1 is the gateway interface for VLAN20 (192.168.20.0/24).",
 show_output="""R1# show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/1      192.168.20.1    YES manual down                  down""",
 expected_fault="The router's VLAN20 gateway interface (Gi0/1) is down."),

dict(case_id="C07", category="Gateway", severity="High", osi_layer="Layer 2/3",
 concept_tag="Duplicate IP / ARP conflict",
 symptom="PC2 receives a correct IP/mask/gateway via DHCP but still cannot ping the gateway.",
 topology_note="VLAN30 gateway should be 192.168.30.1 on R1; a rogue device may be misconfigured on the same segment.",
 show_output="""R1#
%IP-4-DUPADDR: Duplicate address 192.168.30.1 on Vlan30, sourced by 0050.7966.6802""",
 expected_fault="A duplicate IP conflict on the gateway address (192.168.30.1) is breaking ARP resolution intermittently."),

dict(case_id="C08", category="Gateway", severity="High", osi_layer="Layer 3",
 concept_tag="FHRP (HSRP) misconfiguration",
 symptom="When R1 (the active gateway router) is rebooted for maintenance, VLAN10 PCs completely lose their gateway instead of failing over to R2.",
 topology_note="R1 and R2 run HSRP for VLAN10 (192.168.10.0/24), virtual IP 192.168.10.1.",
 show_output="""R1# show standby brief
                     P indicates configured to preempt.
Interface   Grp  Pri P State    Active          Standby         Virtual IP
Vl10        1    100   Init     unknown         local           192.168.10.1""",
 expected_fault="The HSRP group is stuck in Init state (VLAN/interface or priority misconfig), so failover to the standby router never completes."),

# ---------------- DHCP (4) ----------------
dict(case_id="C09", category="DHCP", severity="High", osi_layer="Layer 3",
 concept_tag="DHCP pool exhaustion",
 symptom="New PCs plugged into VLAN10 cannot get a DHCP IP and fall back to a 169.254.x.x address.",
 topology_note="R1 runs DHCP pool VLAN10 (192.168.10.0/24) sized for 10 clients.",
 show_output="""R1# show ip dhcp pool

Pool VLAN10 :
 Utilization mark (high/low)    : 100 / 0
 Subnet size (first/last)       : 0 / 0
 Total addresses                : 10
 Leased addresses               : 10
 Pending event                  : none""",
 expected_fault="The DHCP pool for VLAN10 is fully exhausted (10 of 10 addresses leased)."),

dict(case_id="C10", category="DHCP", severity="High", osi_layer="Layer 3",
 concept_tag="DHCP relay (ip helper-address)",
 symptom="PCs in VLAN20 never receive an IP from the central DHCP server that lives in VLAN10.",
 topology_note="L3 switch has SVIs for VLAN10 and VLAN20; DHCP server sits in VLAN10 only.",
 show_output="""L3SW# show running-config interface vlan20
interface Vlan20
 ip address 192.168.20.1 255.255.255.0
 no ip helper-address""",
 expected_fault="The VLAN20 SVI has no 'ip helper-address' pointing at the DHCP server, so client broadcasts never cross the subnet boundary."),

dict(case_id="C11", category="DHCP", severity="Medium", osi_layer="Layer 3",
 concept_tag="DHCP pool / subnet mismatch",
 symptom="All VLAN10 PCs get an IP from DHCP, but the gateway they receive doesn't match any device on their own subnet.",
 topology_note="VLAN10 SVI is actually 192.168.11.1/24; the DHCP pool was configured before an IP re-numbering.",
 show_output="""R1# show run | section dhcp
ip dhcp pool VLAN10_POOL
 network 192.168.10.0 255.255.255.0
 default-router 192.168.11.1
 dns-server 8.8.8.8""",
 expected_fault="The DHCP pool's network statement (192.168.10.0/24) and default-router (192.168.11.1) point to two different subnets."),

dict(case_id="C12", category="DHCP", severity="Medium", osi_layer="Layer 3",
 concept_tag="DHCP excluded-address misconfiguration",
 symptom="Wireless clients in VLAN40 never receive a DHCP-assigned IP, though the pool and helper address look correct.",
 topology_note="VLAN40 DHCP pool covers 192.168.40.0/24 for wireless clients.",
 show_output="""R1# show run | include excluded
ip dhcp excluded-address 192.168.40.1 192.168.40.254""",
 expected_fault="The excluded-address range (192.168.40.1-192.168.40.254) covers the entire usable host range, leaving zero addresses for clients."),

# ---------------- DNS (4) ----------------
dict(case_id="C13", category="DNS", severity="Medium", osi_layer="Layer 7",
 concept_tag="DNS client misconfiguration",
 symptom="PC3 can ping any IP address successfully, but 'ping server.local' fails to resolve.",
 topology_note="Internal DNS server 192.168.10.5 hosts records for *.local; PC3 is on VLAN10.",
 show_output="""PC3> ipconfig /all
IP Address......................: 192.168.10.20
Subnet Mask......................: 255.255.255.0
Default Gateway..................: 192.168.10.1
DNS Server.......................: 8.8.4.4

PC3> ping server.local
Ping request could not find host server.local. Please check the name and try again.""",
 expected_fault="PC3 points at a public DNS server (8.8.4.4) that has no record for server.local, instead of the internal DNS server."),

dict(case_id="C14", category="DNS", severity="High", osi_layer="Layer 4",
 concept_tag="ACL blocking DNS (port 53)",
 symptom="The internal DNS server is up and PCs use the correct DNS IP, but every lookup times out.",
 topology_note="R1 sits between VLAN10 clients and the DNS server; ACL 101 filters traffic on that path.",
 show_output="""R1# show access-lists 101
Extended IP access list 101
    10 deny udp any any eq 53
    20 permit ip any any""",
 expected_fault="Extended ACL 101 denies UDP port 53 (DNS), blocking all DNS queries from reaching the server."),

dict(case_id="C15", category="DNS", severity="Low", osi_layer="Layer 7",
 concept_tag="Stale DNS record",
 symptom="Most internal sites resolve fine by name, but 'webserver.local' always resolves to the wrong host.",
 topology_note="Internal DNS server holds static host entries for internal servers.",
 show_output="""DNS-Server# show hosts
Host                 Flags       Age Type  Address(es)
webserver.local       (perm, OK)  0   IP    192.168.10.99""",
 expected_fault="The DNS host entry for webserver.local points to a stale/incorrect IP (192.168.10.99 instead of 192.168.10.50)."),

dict(case_id="C16", category="DNS", severity="Medium", osi_layer="Layer 3",
 concept_tag="DHCP option 6 (DNS) missing",
 symptom="PCs on VLAN30 cannot resolve any hostname, while VLAN10 PCs resolve normally.",
 topology_note="VLAN30 clients get addressing from DHCP pool VLAN30_POOL on R1.",
 show_output="""R1# show run | section VLAN30_POOL
ip dhcp pool VLAN30_POOL
 network 192.168.30.0 255.255.255.0
 default-router 192.168.30.1""",
 expected_fault="The VLAN30 DHCP pool has no 'dns-server' statement, so clients never receive a DNS server address."),

# ---------------- Routing (4) ----------------
dict(case_id="C17", category="Routing", severity="High", osi_layer="Layer 3",
 concept_tag="Missing static/dynamic route",
 symptom="HQ PCs on VLAN10 cannot reach the branch office server on 10.10.20.0/24, but local VLAN10 traffic works fine.",
 topology_note="R1 (HQ) connects to BR1 (Branch) via a serial WAN link; the branch LAN subnet is 10.10.20.0/24, reachable only if HQ has a route to it.",
 show_output="""R1# show ip route
Gateway of last resort is not set

C    192.168.10.0/24 is directly connected, GigabitEthernet0/1
C    10.10.10.0/24 is directly connected, Serial0/0/0""",
 expected_fault="R1 has no route (static or dynamic) to the branch subnet 10.10.20.0/24."),

dict(case_id="C18", category="Routing", severity="High", osi_layer="Layer 3",
 concept_tag="OSPF area mismatch",
 symptom="BR1 can ping R1's WAN interface directly but cannot reach any host on R1's LAN side.",
 topology_note="R1 and BR1 run OSPF over the WAN link to exchange LAN routes.",
 show_output="""BR1# show ip ospf neighbor
(no output - no neighbors)

BR1# show ip protocols | include area
  Routing for Networks:
    10.10.10.0 0.0.0.3 area 1""",
 expected_fault="OSPF adjacency never forms because BR1's WAN interface is in area 1 while R1's matching interface is in area 0."),

dict(case_id="C19", category="Routing", severity="Medium", osi_layer="Layer 3",
 concept_tag="Subnet mask misconfiguration",
 symptom="A newly added PC (192.168.10.200) cannot communicate with any other host on the same VLAN10 subnet, including the gateway.",
 topology_note="VLAN10 uses a 255.255.255.0 mask everywhere on this network; R1 Gi0/1 is configured to match.",
 show_output="""PC7> ipconfig
IP Address......................: 192.168.10.200
Subnet Mask......................: 255.255.255.192
Default Gateway..................: 192.168.10.1

R1# show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/1      192.168.10.1    YES manual up                    up
R1# show running-config interface gi0/1
 ip address 192.168.10.1 255.255.255.0""",
 expected_fault="The new PC was configured with a /26 mask (255.255.255.192) instead of /24, putting it on a different logical subnet."),

dict(case_id="C20", category="Routing", severity="Medium", osi_layer="Layer 3",
 concept_tag="Static route bad next-hop",
 symptom="A new finance subnet 172.16.5.0/24 was added behind R1; a static route was configured, but the subnet is still unreachable.",
 topology_note="R1 was given a static route toward 172.16.5.0/24, but the route never appears in the routing table.",
 show_output="""R1# show run | include ip route
ip route 172.16.5.0 255.255.255.0 192.168.99.99

R1# show ip route 192.168.99.0
% Network not in table""",
 expected_fault="The static route's next-hop (192.168.99.99) is not on any directly connected network, so the route never installs (recursive lookup fails)."),

# ---------------- ACL (4) ----------------
dict(case_id="C21", category="ACL", severity="High", osi_layer="Layer 3/4",
 concept_tag="ACL blocking source subnet",
 symptom="PC in VLAN10 gets a valid IP and can ping its gateway, but cannot reach the server in VLAN30.",
 topology_note="R1 routes between VLAN10 and VLAN30; a standard ACL is applied on the path to the server.",
 show_output="""R1# show access-lists
Standard IP access list 10
    10 deny   192.168.10.0, wildcard bits 0.0.0.255
    20 permit any

R1# show ip interface gi0/2 | include access list
  Outgoing access list is 10
  Inbound  access list is not set""",
 expected_fault="Standard ACL 10, applied outbound on Gi0/2, explicitly denies the 192.168.10.0/24 source subnet before it reaches the server."),

dict(case_id="C22", category="ACL", severity="Medium", osi_layer="Layer 4",
 concept_tag="VTY access-class ACL",
 symptom="The admin's PC (moved to a new IP, 192.168.10.100) can no longer SSH into R1 for management, though the router itself is reachable by ping.",
 topology_note="R1's VTY lines use access-class 5 to restrict SSH/Telnet access to trusted management hosts.",
 show_output="""R1# show run | section line vty
line vty 0 4
 access-class 5 in
 login local

R1# show access-lists 5
Standard IP access list 5
    10 permit 192.168.10.50""",
 expected_fault="ACL 5 on the VTY lines only permits 192.168.10.50; the admin's new IP (192.168.10.100) is not in the permit list."),

dict(case_id="C23", category="ACL", severity="Critical", osi_layer="Layer 3",
 concept_tag="Missing security ACL",
 symptom="Guest Wi-Fi users (VLAN40) can reach the internal file server, which should be isolated from guest traffic.",
 topology_note="VLAN40 (Guest) should be restricted from reaching internal server subnets by an ACL on R1's Gi0/3.",
 show_output="""R1# show ip interface gi0/3 | include access list
  Outgoing access list is not set
  Inbound  access list is not set""",
 expected_fault="No ACL is applied to Gi0/3 (the Guest VLAN interface) at all, so the guest-isolation policy was never enforced."),

dict(case_id="C24", category="ACL", severity="Medium", osi_layer="Layer 4",
 concept_tag="Overly broad ACL entry",
 symptom="An ACL was added to block Telnet (port 23) to the server, but web browsing (HTTP) to the same server also stopped working.",
 topology_note="Extended ACL 110 is applied to protect server 192.168.10.50.",
 show_output="""R1# show access-lists 110
Extended IP access list 110
    10 deny tcp any host 192.168.10.50
    20 permit ip any any""",
 expected_fault="ACL 110's deny line has no 'eq 23', so it blocks all TCP to the server instead of just Telnet."),

# ---------------- NAT (3) ----------------
dict(case_id="C25", category="NAT", severity="High", osi_layer="Layer 3",
 concept_tag="NAT inside/outside interface not set",
 symptom="Internal PCs can reach each other but cannot reach any website on the internet.",
 topology_note="R1 should NAT-overload internal VLAN10 traffic out GigabitEthernet0/0 to the ISP.",
 show_output="""R1# show ip nat translations
(empty)

R1# show run | include nat
ip nat inside source list 1 interface GigabitEthernet0/0 overload
interface GigabitEthernet0/1
 ip address 192.168.10.1 255.255.255.0""",
 expected_fault="GigabitEthernet0/1 (the inside VLAN10 interface) is missing the 'ip nat inside' command, so no traffic is ever marked for translation."),

dict(case_id="C26", category="NAT", severity="Medium", osi_layer="Layer 3",
 concept_tag="Static NAT / port-forward typo",
 symptom="The internal web server should be reachable from the internet on port 80, but external requests time out.",
 topology_note="R1 has a static NAT entry mapping public IP 203.0.113.5:80 to the internal web server 192.168.10.80:80.",
 show_output="""R1# show run | include ip nat inside source static
ip nat inside source static tcp 192.168.10.8 80 203.0.113.5 80""",
 expected_fault="The static NAT entry has a typo - it maps to 192.168.10.8 instead of the real server IP 192.168.10.80."),

dict(case_id="C27", category="NAT", severity="Medium", osi_layer="Layer 3",
 concept_tag="NAT ACL scope too narrow",
 symptom="Most PCs on VLAN10 can browse the internet, but hosts numbered 192.168.10.150 and above never get translated.",
 topology_note="NAT overload uses access-list 1 to decide which VLAN10 hosts get translated.",
 show_output="""R1# show access-lists 1
Standard IP access list 1
    10 permit 192.168.10.0, wildcard bits 0.0.0.15""",
 expected_fault="ACL 1's wildcard mask (0.0.0.15) only covers 192.168.10.0-15, a /28 instead of the full /24 subnet."),

# ---------------- Wireless (3) ----------------
dict(case_id="C28", category="Wireless", severity="High", osi_layer="Layer 2",
 concept_tag="WLAN-to-VLAN interface mapping",
 symptom="A laptop connects to CorpWiFi with a strong signal but shows 'limited connectivity' and has no internet access.",
 topology_note="The WLC maps SSID CorpWiFi (WLAN 1) to a VLAN interface for client traffic.",
 show_output="""WLC# show wlan 1
WLAN Identifier.................................. 1
Network Name (SSID)............................. CorpWiFi
Interface........................................ management""",
 expected_fault="WLAN 1 is mapped to the 'management' interface/VLAN instead of the intended 'employee-data' VLAN, so clients land on an isolated subnet."),

dict(case_id="C29", category="Wireless", severity="High", osi_layer="Layer 2 / AAA",
 concept_tag="RADIUS server unreachable",
 symptom="Some laptops connect to the WPA2-Enterprise WiFi fine, but many others get repeated 'authentication failed' errors.",
 topology_note="The WLC authenticates WPA2-Enterprise clients against a RADIUS server at 192.168.99.10.",
 show_output="""WLC# show radius summary
Server Index...  Server Address... Port... State
1                 192.168.99.10     1812    DOWN""",
 expected_fault="The RADIUS server (192.168.99.10) is unreachable/down, so authentication requests time out for most clients."),

dict(case_id="C30", category="Wireless", severity="Medium", osi_layer="Layer 1/2",
 concept_tag="AP disassociated from WLC",
 symptom="WiFi coverage drops to zero in the East Wing conference room while every other area is fine.",
 topology_note="Each area is served by a dedicated AP registered to the WLC.",
 show_output="""WLC# show ap summary
AP Name       Ethernet MAC       Location       Country IP Address     State
AP-Lobby      aabb.cc00.1001     Lobby          US      192.168.50.11  Registered
AP-EastWing   aabb.cc00.1002     EastWing       US      192.168.50.12  Disassociated""",
 expected_fault="The East Wing access point has lost its connection to the WLC (Disassociated) - likely a cable, PoE, or switch port issue."),
]

# ---------------------------------------------------------------------------
# 2. AI DIAGNOSIS + HUMAN REVIEW  (one entry per case, same order as above)
# ---------------------------------------------------------------------------
# verdict: Accepted | Edited | Rejected
reviews = {
"C01": dict(ai_root_cause="Fa0/3 is in the wrong VLAN (default VLAN1 instead of VLAN10).",
    ai_confidence="High", ai_evidence="show vlan brief lists Fa0/3 under VLAN1; running-config confirms switchport access vlan 1.",
    ai_next_command="show running-config interface fa0/3", ai_fix_steps="On SW1: interface fa0/3 -> switchport access vlan 10.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Matches the known fault exactly, evidence is direct."),

"C02": dict(ai_root_cause="VLAN10 is missing from the trunk's allowed-VLAN list on Gi0/1.",
    ai_confidence="High", ai_evidence="show interfaces trunk lists allowed vlans as 1,20,30 - no 10.",
    ai_next_command="show interfaces gi0/1 switchport", ai_fix_steps="switchport trunk allowed vlan add 10 on Gi0/1 (both switches).",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct call, evidence quoted directly from output."),

"C03": dict(ai_root_cause="VLAN30 SVI (interface Vlan30) is administratively down.",
    ai_confidence="High", ai_evidence="show ip interface brief shows Vlan30 status = administratively down.",
    ai_next_command="show running-config interface vlan30", ai_fix_steps="interface vlan30 -> no shutdown.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Clean, single-command confirmation."),

"C04": dict(ai_root_cause="Trunk between SW1 and SW2 is not configured, so VLAN10 traffic never crosses.",
    ai_confidence="Medium", ai_evidence="CDP message references Gi0/1 on both switches.",
    ai_next_command="show interfaces gi0/1 switchport", ai_fix_steps="Re-enable trunking with switchport mode trunk on both ends.",
    verdict="Edited", corrected_diagnosis="Native VLAN mismatch (SW1=VLAN1, SW2=VLAN10) on an already-trunking link, not a missing trunk.",
    reviewer_notes="The AI misread the CDP message. The trunk IS up (Status: trunking); the log is a native VLAN mismatch warning, not a down trunk. Fix is to match native VLAN on both sides, not re-trunk."),

"C05": dict(ai_root_cause="PC1 has the wrong default gateway configured (192.168.10.254 vs router's 192.168.10.1).",
    ai_confidence="High", ai_evidence="PC ipconfig gateway differs from R1 Gi0/0 IP in show ip interface brief.",
    ai_next_command="show ip interface brief on R1", ai_fix_steps="Reconfigure PC1 (or DHCP scope) with gateway 192.168.10.1.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Direct IP comparison, no ambiguity."),

"C06": dict(ai_root_cause="Gateway interface Gi0/1 on R1 is down, cutting off all of VLAN20.",
    ai_confidence="High", ai_evidence="show ip interface brief: Gi0/1 status/protocol both down.",
    ai_next_command="show interfaces gi0/1", ai_fix_steps="Check cable/SFP, then no shutdown on Gi0/1 if administratively down.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Straightforward, matches known fault."),

"C07": dict(ai_root_cause="Duplicate IP address conflict on the gateway address 192.168.30.1.",
    ai_confidence="Medium", ai_evidence="%IP-4-DUPADDR syslog message names 192.168.30.1.",
    ai_next_command="show arp | include 192.168.30.1", ai_fix_steps="Locate and reconfigure the rogue device using 0050.7966.6802; remove the static/duplicate IP.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Confidence correctly kept at Medium since the rogue device itself isn't identified yet - reasonable."),

"C08": dict(ai_root_cause="Gateway interface on R1 is physically down, so HSRP can't fail over.",
    ai_confidence="Medium", ai_evidence="show standby brief output shows an unusual state.",
    ai_next_command="show ip interface brief on R1", ai_fix_steps="Check R1's physical interface and cabling.",
    verdict="Rejected", corrected_diagnosis="HSRP group stuck in Init state (FHRP misconfiguration - likely VLAN/interface or version mismatch between R1 and R2), unrelated to physical interface status.",
    reviewer_notes="The AI guessed 'interface down' without actually reading the standby brief table - the State column clearly says Init, not the Active/Standby state you'd see after a normal failover. There is no evidence in the output of a physical link problem. Re-prompted with the correct focus on HSRP state."),

"C09": dict(ai_root_cause="DHCP pool VLAN10 is exhausted (10/10 addresses leased).",
    ai_confidence="High", ai_evidence="show ip dhcp pool: Leased addresses = 10, Total addresses = 10.",
    ai_next_command="show ip dhcp binding", ai_fix_steps="Enlarge the pool or shorten the lease time; check for stale bindings to clear.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Numbers speak for themselves."),

"C10": dict(ai_root_cause="VLAN20 SVI has no ip helper-address, so DHCP broadcasts never reach the server in VLAN10.",
    ai_confidence="High", ai_evidence="show running-config interface vlan20 shows 'no ip helper-address'.",
    ai_next_command="show running-config interface vlan10", ai_fix_steps="Add ip helper-address <DHCP-server-IP> under interface vlan20.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct and directly evidenced."),

"C11": dict(ai_root_cause="DHCP pool VLAN10_POOL is exhausted.",
    ai_confidence="Medium", ai_evidence="Pool configuration was reviewed.",
    ai_next_command="show ip dhcp pool VLAN10_POOL", ai_fix_steps="Increase pool size.",
    verdict="Edited", corrected_diagnosis="The pool's network statement (192.168.10.0/24) and default-router (192.168.11.1) belong to two different subnets - a leftover from IP re-numbering, not exhaustion.",
    reviewer_notes="The AI assumed exhaustion without checking utilization - the output given doesn't even show a lease count. The real mismatch is visible right in the network/default-router lines. Correction is a config edit, not a bigger pool."),

"C12": dict(ai_root_cause="Excluded-address range 192.168.40.1-192.168.40.254 leaves no addresses for DHCP clients.",
    ai_confidence="High", ai_evidence="show run | include excluded shows the full host range excluded.",
    ai_next_command="show ip dhcp pool", ai_fix_steps="Narrow the excluded range to only the addresses actually reserved (e.g. gateway, AP management IPs).",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Matches evidence exactly."),

"C13": dict(ai_root_cause="PC3 is configured with a public DNS server (8.8.4.4) that has no record for the internal name server.local.",
    ai_confidence="High", ai_evidence="ipconfig /all shows DNS Server: 8.8.4.4; internal DNS server is 192.168.10.5.",
    ai_next_command="nslookup server.local 192.168.10.5", ai_fix_steps="Point PC3 (or the DHCP scope) at the internal DNS server 192.168.10.5.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Clean diagnosis."),

"C14": dict(ai_root_cause="Extended ACL 101 denies UDP port 53, blocking DNS.",
    ai_confidence="High", ai_evidence="show access-lists 101 line 10: deny udp any any eq 53.",
    ai_next_command="show ip interface gi0/0 | include access list", ai_fix_steps="Remove or edit ACE 10 in ACL 101, or add a permit above it for the DNS server's IP.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Direct match."),

"C15": dict(ai_root_cause="webserver.local has a stale DNS record pointing to 192.168.10.99 instead of .50.",
    ai_confidence="Medium", ai_evidence="show hosts entry for webserver.local lists 192.168.10.99.",
    ai_next_command="ping 192.168.10.50", ai_fix_steps="Update/re-register the host entry for webserver.local to 192.168.10.50.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Confidence correctly kept Medium since the 'correct' IP is only known from the topology note, not the output itself."),

"C16": dict(ai_root_cause="VLAN30 DHCP pool has no dns-server line, so clients get no DNS server.",
    ai_confidence="High", ai_evidence="show run | section VLAN30_POOL has no dns-server statement.",
    ai_next_command="show ip dhcp pool VLAN30_POOL", ai_fix_steps="Add 'dns-server <IP>' to the VLAN30_POOL configuration.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct, evidence is an absence which the AI correctly flagged."),

"C17": dict(ai_root_cause="R1 has no route to the branch subnet 10.10.20.0/24.",
    ai_confidence="High", ai_evidence="show ip route lists only 192.168.10.0/24 and 10.10.10.0/24, no 10.10.20.0/24.",
    ai_next_command="show ip route 10.10.20.0", ai_fix_steps="Add a static route (ip route 10.10.20.0 255.255.255.0 <next-hop>) or enable a routing protocol toward BR1.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Matches evidence and known fault."),

"C18": dict(ai_root_cause="OSPF neighbor never forms because BR1's interface is in area 1 while R1's is in area 0.",
    ai_confidence="Medium", ai_evidence="show ip ospf neighbor returns nothing; show ip protocols shows area 1 on BR1's WAN network.",
    ai_next_command="show ip protocols on R1", ai_fix_steps="Match the area ID on both sides of the WAN link (both should be area 0, or whatever the design calls for).",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Good reasoning - flagged that R1's side still needs to be checked to confirm, hence Medium and not High."),

"C19": dict(ai_root_cause="Duplicate IP conflict is preventing the new PC from communicating.",
    ai_confidence="Medium", ai_evidence="New PC (192.168.10.200) can't reach anything on the subnet.",
    ai_next_command="show ip arp | include 192.168.10.200", ai_fix_steps="Check for another device using 192.168.10.200 and reassign one of them.",
    verdict="Rejected", corrected_diagnosis="Subnet mask misconfiguration - the PC is using 255.255.255.192 (/26) while the rest of VLAN10 uses 255.255.255.0 (/24), so it's logically on a different subnet.",
    reviewer_notes="No duplicate-IP evidence exists anywhere in the output (no DUPADDR message, no ARP conflict log) - the AI guessed based on the symptom alone instead of reading the ipconfig output, which clearly shows a different mask than the router's interface."),

"C20": dict(ai_root_cause="Static route to 172.16.5.0/24 has a next-hop (192.168.99.99) that isn't reachable, so the route never installs.",
    ai_confidence="High", ai_evidence="show ip route 192.168.99.0 returns '% Network not in table', confirming the next-hop can't be resolved.",
    ai_next_command="show ip route 172.16.5.0", ai_fix_steps="Correct the next-hop IP, or reference the correct exit interface instead of an IP.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct and precisely evidenced."),

"C21": dict(ai_root_cause="Standard ACL 10 (outbound on Gi0/2) denies the 192.168.10.0/24 source subnet.",
    ai_confidence="Medium", ai_evidence="show access-lists: ACL10 line 10 denies 192.168.10.0/0.0.0.255; ACL10 is set outbound on Gi0/2.",
    ai_next_command="show ip route; show access-lists; show interfaces trunk", ai_fix_steps="Add a permit line above the deny for the required traffic, or remove ACL10 from Gi0/2 if it's not needed there.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="This matches the example diagnosis format given in the problem statement almost exactly - good sign the prompt is well-calibrated."),

"C22": dict(ai_root_cause="ACL 5 on the VTY lines only permits 192.168.10.50; the admin's new IP isn't listed.",
    ai_confidence="High", ai_evidence="show access-lists 5 has a single permit line for 192.168.10.50.",
    ai_next_command="show run | section line vty", ai_fix_steps="Add 'permit 192.168.10.100' to ACL 5 (or replace the old entry if the admin's IP changed permanently).",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct, simple fix identified."),

"C23": dict(ai_root_cause="No ACL is applied to Gi0/3 at all, so guest traffic isn't isolated.",
    ai_confidence="High", ai_evidence="show ip interface gi0/3 confirms both inbound and outbound access lists are 'not set'.",
    ai_next_command="show access-lists", ai_fix_steps="Create and apply an ACL on Gi0/3 that denies guest VLAN traffic to internal server subnets, permits internet-bound traffic.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="This is the Critical/security case - human reviewer double-checked personally given the severity, and agreed with the AI."),

"C24": dict(ai_root_cause="ACL 110 is blocking Telnet to the server (192.168.10.50).",
    ai_confidence="Medium", ai_evidence="show access-lists 110 shows a deny tcp line targeting the server.",
    ai_next_command="show access-lists 110", ai_fix_steps="Remove ACL 110 from the interface to restore access.",
    verdict="Edited", corrected_diagnosis="ACL 110's deny line is missing 'eq 23', so it blocks ALL TCP (including HTTP) to the server, not just Telnet as intended.",
    reviewer_notes="AI correctly found the ACL but the suggested fix (removing it entirely) would also remove the intended Telnet block. Correct fix is to add 'eq 23' to the deny line, not delete the ACL."),

"C25": dict(ai_root_cause="Gi0/1 is missing 'ip nat inside', so no traffic is ever marked for translation.",
    ai_confidence="High", ai_evidence="show ip nat translations is empty; show run confirms Gi0/1 has no ip nat inside line.",
    ai_next_command="show run interface gi0/0", ai_fix_steps="Add 'ip nat inside' under Gi0/1 (the VLAN10-facing interface).",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct and directly evidenced."),

"C26": dict(ai_root_cause="The static NAT entry has a typo - maps to 192.168.10.8 instead of 192.168.10.80.",
    ai_confidence="High", ai_evidence="show run | include static shows 'tcp 192.168.10.8 80 ...' vs the real server IP 192.168.10.80.",
    ai_next_command="ping 192.168.10.80", ai_fix_steps="Remove the incorrect static NAT line and re-add it with 192.168.10.80.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct, simple typo catch."),

"C27": dict(ai_root_cause="ACL 1's wildcard mask (0.0.0.15) only covers a /28, not the full /24 VLAN10 subnet.",
    ai_confidence="High", ai_evidence="show access-lists 1: permit 192.168.10.0 wildcard bits 0.0.0.15.",
    ai_next_command="show ip nat translations", ai_fix_steps="Change the wildcard mask to 0.0.0.255 to cover the full /24 subnet.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct math on the wildcard mask."),

"C28": dict(ai_root_cause="WLAN 1 is mapped to the 'management' interface instead of the employee-data VLAN.",
    ai_confidence="High", ai_evidence="show wlan 1 lists Interface: management.",
    ai_next_command="show interface employee-data", ai_fix_steps="Change WLAN 1's interface mapping to employee-data under the WLC's WLAN config.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Correct and direct."),

"C29": dict(ai_root_cause="WPA2 passphrase mismatch is causing authentication failures for some clients.",
    ai_confidence="Medium", ai_evidence="Multiple clients failing to authenticate to the same SSID.",
    ai_next_command="show wlan 1 security", ai_fix_steps="Re-push the correct WPA2 passphrase to affected clients.",
    verdict="Rejected", corrected_diagnosis="RADIUS server (192.168.99.10) is unreachable/down - this is WPA2-Enterprise (802.1X), not a shared passphrase (WPA2-Personal), so a passphrase mismatch doesn't apply here at all.",
    reviewer_notes="The AI assumed WPA2-Personal without checking the topology note, which explicitly says WPA2-Enterprise with a RADIUS server. The 'show radius summary' output was sitting right there showing State: DOWN and the AI didn't use it."),

"C30": dict(ai_root_cause="AP-EastWing has lost its connection to the WLC (Disassociated state).",
    ai_confidence="High", ai_evidence="show ap summary: AP-EastWing State = Disassociated, all other APs = Registered.",
    ai_next_command="show cdp neighbor detail on the EastWing switch port", ai_fix_steps="Check the switch port, PoE budget, and cable feeding AP-EastWing; re-seat/replace as needed.",
    verdict="Accepted", corrected_diagnosis="", reviewer_notes="Clear single-line evidence, correct call."),
}

# ---------------------------------------------------------------------------
# 3. WRITE cases.csv
# ---------------------------------------------------------------------------
case_fields = ["case_id", "category", "symptom", "topology_note", "show_output",
               "expected_fault", "osi_layer", "concept_tag", "severity"]

with open("cases.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=case_fields)
    w.writeheader()
    for c in cases:
        w.writerow({k: c[k] for k in case_fields})

# ---------------------------------------------------------------------------
# 4. WRITE ai_diagnosis_log.csv
# ---------------------------------------------------------------------------
ai_fields = ["case_id", "ai_root_cause", "ai_confidence", "ai_evidence", "ai_next_command", "ai_fix_steps"]
with open("ai_diagnosis_log.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=ai_fields)
    w.writeheader()
    for c in cases:
        r = reviews[c["case_id"]]
        w.writerow({
            "case_id": c["case_id"],
            "ai_root_cause": r["ai_root_cause"],
            "ai_confidence": r["ai_confidence"],
            "ai_evidence": r["ai_evidence"],
            "ai_next_command": r["ai_next_command"],
            "ai_fix_steps": r["ai_fix_steps"],
        })

# ---------------------------------------------------------------------------
# 5. WRITE human_review_log.csv
# ---------------------------------------------------------------------------
human_fields = ["case_id", "ai_root_cause", "human_verdict", "corrected_diagnosis", "reviewer_notes"]
with open("human_review_log.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=human_fields)
    w.writeheader()
    for c in cases:
        r = reviews[c["case_id"]]
        w.writerow({
            "case_id": c["case_id"],
            "ai_root_cause": r["ai_root_cause"],
            "human_verdict": r["verdict"],
            "corrected_diagnosis": r["corrected_diagnosis"],
            "reviewer_notes": r["reviewer_notes"],
        })

print(f"Wrote {len(cases)} cases.")
verdict_counts = {}
for r in reviews.values():
    verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1
print("Verdict counts:", verdict_counts)
