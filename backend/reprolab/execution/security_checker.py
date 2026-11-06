"""AST Static Security Checker for ReproLab (Milestone 3).

Complies with:
- docs/threat-model.md §AS-7 & OWASP ASI05 (Unexpected Code Execution / RCE)
- Audits Python scripts prior to container sandbox execution
- Flags prohibited modules (os, sys, subprocess, socket, pty, shutil, etc.)
- Flags dangerous builtins (eval, exec, __import__, compile)
- Emits OpenTelemetry span stage7.security.ast_precheck
"""

import ast
from dataclasses import dataclass, field
from typing import List, Optional

from reprolab.core.telemetry import trace_span


PROHIBITED_MODULES = frozenset({
    "os",
    "sys",
    "subprocess",
    "socket",
    "pty",
    "shutil",
    "importlib",
    "posix",
    "nt",
    "winreg",
    "ctypes",
    "multiprocessing",
    "signal",
    "asyncio.subprocess",
    "builtins",
    "__builtin__",
    "pickle",
    "_pickle",
    "shelve",
    "marshal",
    "dbm",
})

DANGEROUS_BUILTINS = frozenset({
    "eval",
    "exec",
    "__import__",
    "compile",
    "globals",
    "locals",
    "breakpoint",
})


@dataclass
class SecurityViolation:
    rule_id: str
    message: str
    line_number: int


class ASTSecurityError(Exception):
    """Raised when an AST check identifies a security violation in code."""

    def __init__(self, message: str, violations: Optional[List[SecurityViolation]] = None):
        super().__init__(message)
        self.violations = violations or []


@dataclass
class SecurityCheckResult:
    is_safe: bool
    violations: List[SecurityViolation] = field(default_factory=list)


class ASTSecurityVisitor(ast.NodeVisitor):
    """Walks Python AST to inspect imports, calls, and attribute lookups."""

    def __init__(self):
        self.violations: List[SecurityViolation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base_module = alias.name.split(".")[0]
            if base_module in PROHIBITED_MODULES:
                self.violations.append(
                    SecurityViolation(
                        rule_id="PROHIBITED_MODULE_IMPORT",
                        message=f"Import of prohibited module '{alias.name}' detected.",
                        line_number=node.lineno,
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            base_module = node.module.split(".")[0]
            if base_module in PROHIBITED_MODULES:
                self.violations.append(
                    SecurityViolation(
                        rule_id="PROHIBITED_MODULE_IMPORT",
                        message=f"From-import from prohibited module '{node.module}' detected.",
                        line_number=node.lineno,
                    )
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in DANGEROUS_BUILTINS:
            self.violations.append(
                SecurityViolation(
                    rule_id="DANGEROUS_BUILTIN_CALL",
                    message=f"Invocation of dangerous function '{func_name}' detected.",
                    line_number=node.lineno,
                )
            )
        self.generic_visit(node)


class ASTSecurityChecker:
    """Pre-execution static analysis auditor for reproduction scripts."""

    def audit_script(self, code_content: str, case_id: Optional[str] = None) -> SecurityCheckResult:
        with trace_span("stage7.security.ast_precheck", case_id=case_id) as span:
            try:
                tree = ast.parse(code_content)
            except SyntaxError as e:
                violation = SecurityViolation(
                    rule_id="SYNTAX_ERROR",
                    message=f"Script syntax error: {e}",
                    line_number=e.lineno or 1,
                )
                span.set_attribute("security.is_safe", False)
                span.set_attribute("security.violations_count", 1)
                return SecurityCheckResult(is_safe=False, violations=[violation])

            visitor = ASTSecurityVisitor()
            visitor.visit(tree)

            is_safe = len(visitor.violations) == 0
            span.set_attribute("security.is_safe", is_safe)
            span.set_attribute("security.violations_count", len(visitor.violations))

            return SecurityCheckResult(is_safe=is_safe, violations=visitor.violations)

    def check_script(self, code_content: str, case_id: Optional[str] = None):
        result = self.audit_script(code_content, case_id=case_id)
        return result.is_safe, result.violations

    def assert_safe(self, code_content: str, case_id: Optional[str] = None) -> None:
        result = self.audit_script(code_content, case_id=case_id)
        if not result.is_safe:
            msg = "; ".join(v.message for v in result.violations)
            raise ASTSecurityError(f"Security violation detected: {msg}", violations=result.violations)

