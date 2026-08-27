# Responsible AI Log

This log records every case where the human reviewer disagreed with the AI's
diagnosis - either editing it (AI was partly right) or rejecting it (AI was
wrong). Full details for all 30 cases are in `human_review_log.csv`; this
file pulls out the corrected ones and explains them in plain language,
because that's the part a grader actually wants to read.

Out of 30 cases: **24 Accepted, 3 Edited, 3 Rejected** -> the AI's raw
answer was usable as-is 80% of the time, and needed a human catch the other
20% of the time. That's the whole point of the "human review" safety rule -
without it, 6 wrong or incomplete fixes would have gone out unchecked.

---

## 1. Case C04 - VLAN - Edited

- **AI said:** "Trunk between SW1 and SW2 is not configured, so VLAN10
  traffic never crosses." (Confidence: Medium)
- **What was actually wrong:** Native VLAN mismatch (SW1 = VLAN1, SW2 =
  VLAN10) on a trunk that was already up.
- **Why the AI got it wrong:** It saw a CDP warning message and assumed
  "trunk problem = trunk not configured," without noticing the output
  literally says `Status: trunking`. It never read the message text closely
  enough to see it specifically names a *native VLAN* mismatch, not a down
  trunk.
- **Lesson:** Confidence should drop when the AI is pattern-matching a
  keyword ("trunk," "mismatch") instead of reading the actual state fields.

## 2. Case C08 - Gateway - Rejected

- **AI said:** "Gateway interface on R1 is physically down, so HSRP can't
  fail over." (Confidence: Medium)
- **What was actually wrong:** The HSRP group is stuck in `Init` state - a
  protocol/config issue, not a physical link issue.
- **Why the AI got it wrong:** There's no interface-down evidence anywhere
  in the output it was given (`show standby brief` only). It guessed based
  on the symptom description ("lost their gateway") rather than the
  command output actually provided.
- **Lesson:** This is the clearest case of the AI hypothesizing without
  evidence. Reviewer rejected outright rather than editing, since the fix
  direction (check cabling) was completely wrong and could have wasted an
  engineer's time.

## 3. Case C11 - DHCP - Edited

- **AI said:** "DHCP pool VLAN10_POOL is exhausted." (Confidence: Medium)
- **What was actually wrong:** The pool's `network` statement and
  `default-router` line point to two different subnets - a leftover from an
  IP re-numbering, not exhaustion.
- **Why the AI got it wrong:** "DHCP not working" defaulted to the AI's most
  common DHCP failure mode (exhaustion) instead of reading the specific
  config lines it was given, which don't even mention a lease count.
- **Lesson:** A generic "most likely cause for this category" answer isn't
  the same as an evidence-backed one - the prompt says "only use evidence
  present," and the AI didn't follow that here.

## 4. Case C19 - Routing/Addressing - Rejected

- **AI said:** "Duplicate IP address conflict is preventing the new PC from
  communicating." (Confidence: Medium)
- **What was actually wrong:** Subnet mask misconfiguration - the new PC
  uses `255.255.255.192` (/26) while the rest of VLAN10 uses
  `255.255.255.0` (/24), putting it on a different logical network.
- **Why the AI got it wrong:** There is no duplicate-IP evidence anywhere in
  this case (no `%IP-4-DUPADDR` message, no ARP log) - the AI reused the
  same guess it made correctly on a different case (C07) without checking
  whether the evidence for it actually existed here.
- **Lesson:** Rule checker actually caught this one correctly
  (`wrong_mask` flag) before the AI even ran - a good example of why the
  deterministic checker and the AI are complementary, not redundant.

## 5. Case C24 - ACL - Edited

- **AI said:** "ACL 110 is blocking Telnet to the server." Fix suggested:
  "Remove ACL 110 from the interface to restore access." (Confidence:
  Medium)
- **What was actually wrong:** The AI correctly found the right ACL, but
  the suggested *fix* was wrong - removing ACL 110 entirely would also
  remove the intentional Telnet block. The real fix is adding `eq 23` to
  the deny line so it only matches Telnet, not all TCP.
- **Why the AI got it wrong:** It stopped at "this ACL is the problem"
  without checking whether the fix it proposed actually preserved the
  original intent of the ACL.
- **Lesson:** Root-cause identification and fix-quality are two different
  things to check - the AI can be right about the "what" and still wrong
  about the "how to fix it."

## 6. Case C29 - Wireless - Rejected

- **AI said:** "WPA2 passphrase mismatch is causing authentication
  failures." (Confidence: Medium)
- **What was actually wrong:** The RADIUS server (192.168.99.10) is down -
  this network uses WPA2-Enterprise (802.1X), which doesn't even use a
  shared passphrase.
- **Why the AI got it wrong:** It ignored the topology note, which
  explicitly says "WPA2-Enterprise" and names a RADIUS server, and it
  ignored the `show radius summary` output that was directly in front of
  it showing `State: DOWN`.
- **Lesson:** The most serious miss in this log - all the evidence needed
  was already provided, the AI just didn't use it. This is exactly the kind
  of case the human-review safety rule exists to catch.

---

## Summary table

| Case | Category | AI verdict | Human verdict | Root issue with the AI's answer |
|------|----------|-----------|----------------|----------------------------------|
| C04  | VLAN     | Trunk not configured | Edited | Misread a native-VLAN warning as a down trunk |
| C08  | Gateway  | Interface physically down | Rejected | No evidence given for this at all - pure guess |
| C11  | DHCP     | Pool exhausted | Edited | Defaulted to the common cause instead of reading the config |
| C19  | Routing  | Duplicate IP | Rejected | Reused a pattern from another case with no matching evidence here |
| C24  | ACL      | Right ACL, wrong fix | Edited | Fix would have removed the intended security rule |
| C29  | Wireless | Passphrase mismatch | Rejected | Ignored both the topology note and the RADIUS evidence in front of it |
