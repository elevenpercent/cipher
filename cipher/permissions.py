import os
import re
import fnmatch
import json
import time
from pathlib import Path


class PermissionRule:
    def __init__(self, tool=None, pattern=None, action="ask", reason=""):
        self.tool = tool
        self.pattern = pattern
        self.action = action
        self.reason = reason
        self.created = time.time()
        self.ttl = 0

    def matches(self, tool, args):
        if self.tool and self.tool != tool:
            return False
        if self.pattern:
            return fnmatch.fnmatch(args or "", self.pattern)
        return True

    def expired(self):
        if self.ttl <= 0:
            return False
        return time.time() - self.created > self.ttl

    def to_dict(self):
        return {
            "tool": self.tool,
            "pattern": self.pattern,
            "action": self.action,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d):
        rule = cls(
            tool=d.get("tool"),
            pattern=d.get("pattern"),
            action=d.get("action", "ask"),
            reason=d.get("reason", ""),
        )
        return rule


class PermissionManager:
    CONFIRM_TOOLS = {"run", "write", "edit", "git"}

    def __init__(self, config=None):
        self.config = config or {}
        self.rules = []
        self.session_rules = []
        self._load_rules()

    def _load_rules(self):
        perms = self.config.get("permissions", {})
        if not isinstance(perms, dict):
            return
        for rule_type, rules in perms.items():
            if not isinstance(rules, dict):
                continue
            if rule_type == "auto_allow":
                for t, patterns in rules.items():
                    if not isinstance(patterns, list):
                        continue
                    for p in patterns:
                        self.rules.append(PermissionRule(tool=t, pattern=p, action="allow"))
            elif rule_type == "auto_deny":
                for t, patterns in rules.items():
                    if not isinstance(patterns, list):
                        continue
                    for p in patterns:
                        self.rules.append(PermissionRule(tool=t, pattern=p, action="deny"))

    def check(self, tool, args):
        if tool not in self.CONFIRM_TOOLS:
            return "allow"
        if self.config.get("auto_confirm", False):
            return "allow"
        all_rules = self.rules + self.session_rules
        for rule in all_rules:
            if rule.expired():
                continue
            if rule.matches(tool, args):
                return rule.action
        return "ask"

    def add_session_rule(self, tool, pattern, action, ttl=0):
        rule = PermissionRule(tool=tool, pattern=pattern, action=action)
        rule.ttl = ttl
        self.session_rules.append(rule)

    def allow_once(self, tool, args):
        rule = PermissionRule(tool=tool, pattern=args, action="allow")
        rule.ttl = 10
        self.session_rules.append(rule)

    def to_config_dict(self):
        result = {"auto_allow": {}, "auto_deny": {}}
        for rule in self.rules:
            target = "auto_allow" if rule.action == "allow" else "auto_deny"
            if rule.tool not in result[target]:
                result[target][rule.tool] = []
            if rule.pattern:
                result[target][rule.tool].append(rule.pattern)
        return result
