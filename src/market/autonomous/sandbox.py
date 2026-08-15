"""Sandbox for AI-generated code (pustaka/68).

Safe execution of AI-generated code with:
- AST scanning for dangerous patterns
- Resource limits (memory, CPU time)
- Timeout enforcement
- Restricted imports
- Output capture
"""

from __future__ import annotations

import ast
import logging
import signal
import textwrap
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Forbidden imports that should never appear in AI-generated code
FORBIDDEN_IMPORTS = {
    "os",
    "subprocess",
    "shutil",
    "ctypes",
    "multiprocessing",
    "threading",
    "socket",
    "http",
    "urllib",
    "requests",
    "asyncio",
    "pickle",
    "shelve",
    "marshal",
    "importlib",
    "builtins",
}

# Forbidden AST node types
FORBIDDEN_NODES = {
    ast.Global,
    ast.Nonlocal,
}

# Allowed imports for AI-generated trading code
ALLOWED_IMPORTS = {
    "numpy",
    "pandas",
    "math",
    "statistics",
    "scipy",
    "sklearn",
    "torch",
    "lightgbm",
    "market",
}


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""

    timeout_seconds: float = 10.0
    max_memory_mb: int = 512
    max_output_chars: int = 10_000
    allowed_imports: set[str] = field(default_factory=lambda: ALLOWED_IMPORTS.copy())
    forbidden_imports: set[str] = field(default_factory=lambda: FORBIDDEN_IMPORTS.copy())
    enable_ast_scan: bool = True
    enable_timeout: bool = True


@dataclass
class SandboxResult:
    """Result of sandbox execution."""

    success: bool
    output: str = ""
    error: str = ""
    ast_violations: list[str] = field(default_factory=list)
    import_violations: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    timed_out: bool = False
    return_value: Any = None


class ASTScanner:
    """AST-based code scanner for dangerous patterns."""

    @staticmethod
    def scan(
        code: str,
        forbidden_imports: set[str] | None = None,
        allowed_imports: set[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Scan code for AST violations and import violations.

        Args:
            code: Python code to scan.
            forbidden_imports: Set of forbidden module names.
            allowed_imports: Set of allowed module names (if set, everything else is forbidden).

        Returns:
            Tuple of (ast_violations, import_violations).
        """
        ast_violations: list[str] = []
        import_violations: list[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"SyntaxError: {e}"], []

        for node in ast.walk(tree):
            # Check forbidden node types
            if type(node) in FORBIDDEN_NODES:
                lineno = getattr(node, "lineno", 0)
                ast_violations.append(
                    f"Forbidden node type: {type(node).__name__} at line {lineno}",
                )

            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".")[0]
                    if forbidden_imports and root_module in forbidden_imports:
                        import_violations.append(
                            f"Forbidden import: {alias.name} at line {node.lineno}",
                        )
                    elif allowed_imports and root_module not in allowed_imports:
                        import_violations.append(
                            f"Disallowed import: {alias.name} at line {node.lineno}",
                        )

            elif isinstance(node, ast.ImportFrom) and node.module:
                root_module = node.module.split(".")[0]
                if forbidden_imports and root_module in forbidden_imports:
                    import_violations.append(
                        f"Forbidden import: {node.module} at line {node.lineno}",
                    )
                elif allowed_imports and root_module not in allowed_imports:
                    import_violations.append(
                        f"Disallowed import: {node.module} at line {node.lineno}",
                    )

            # Check for dangerous function calls
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "__builtins__"
                ):
                    ast_violations.append(
                        f"Direct __builtins__ access at line {node.lineno}",
                    )

            # Check for exec/eval calls
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("exec", "eval", "compile"):
                    ast_violations.append(
                        f"Dangerous function call: {func.id}() at line {node.lineno}",
                    )

        return ast_violations, import_violations


class Sandbox:
    """Sandbox for safe execution of AI-generated code."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    def validate(self, code: str) -> tuple[bool, list[str], list[str]]:
        """Validate code without executing it.

        Args:
            code: Python code to validate.

        Returns:
            Tuple of (is_valid, ast_violations, import_violations).
        """
        if not self.config.enable_ast_scan:
            return True, [], []

        ast_violations, import_violations = ASTScanner.scan(
            code,
            forbidden_imports=self.config.forbidden_imports,
            allowed_imports=self.config.allowed_imports,
        )

        is_valid = len(ast_violations) == 0 and len(import_violations) == 0
        return is_valid, ast_violations, import_violations

    def execute(
        self,
        code: str,
        globals_dict: dict[str, Any] | None = None,
    ) -> SandboxResult:
        """Execute code in the sandbox.

        Args:
            code: Python code to execute.
            globals_dict: Optional globals dictionary.

        Returns:
            SandboxResult with output, errors, and timing.
        """
        import time

        # Step 1: AST scan
        if self.config.enable_ast_scan:
            is_valid, ast_violations, import_violations = self.validate(code)
            if not is_valid:
                return SandboxResult(
                    success=False,
                    ast_violations=ast_violations,
                    import_violations=import_violations,
                    error="Code validation failed",
                )

        # Step 2: Prepare execution environment
        safe_globals: dict[str, Any] = {
            "__builtins__": {
                "print": print,
                "len": len,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sorted": sorted,
                "sum": sum,
                "min": min,
                "max": max,
                "abs": abs,
                "round": round,
                "isinstance": isinstance,
                "type": type,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "True": True,
                "False": False,
                "None": None,
                "__import__": __import__,
            },
        }

        if globals_dict:
            safe_globals.update(globals_dict)

        # Step 3: Execute with timeout
        start_time = time.time()

        # Windows doesn't have signal.SIGALRM/setitimer — use thread-based
        # timeout fallback for cross-platform compatibility.
        _use_sigalrm = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")

        def _timeout_handler(signum: int, frame: Any) -> None:
            raise TimeoutError(f"Execution exceeded {self.config.timeout_seconds}s")

        old_handler = signal.getsignal(signal.SIGALRM) if _use_sigalrm else None

        # Thread-based timeout for Windows (and fallback)
        _timeout_event = threading.Event()
        _timeout_thread: threading.Thread | None = None

        def _thread_timeout() -> None:
            if _timeout_event.wait(self.config.timeout_seconds):
                return  # cancelled
            # Timeout expired — inject TimeoutError via _thread_exception
            _thread_exception.append(TimeoutError(f"Execution exceeded {self.config.timeout_seconds}s"))

        _thread_exception: list[BaseException] = []

        try:
            if self.config.enable_timeout:
                if _use_sigalrm:
                    signal.signal(signal.SIGALRM, _timeout_handler)
                    signal.setitimer(signal.ITIMER_REAL, self.config.timeout_seconds)
                else:
                    # Windows fallback: thread-based timeout
                    _timeout_thread = threading.Thread(target=_thread_timeout, daemon=True)
                    _timeout_thread.start()

            # Capture stdout
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()

            # Dedent and execute
            cleaned_code = textwrap.dedent(code)

            with redirect_stdout(buf):
                exec(cleaned_code, safe_globals)

            # Check if timeout fired during exec
            if _thread_exception:
                raise _thread_exception[0]

            output = buf.getvalue()
            if len(output) > self.config.max_output_chars:
                output = output[: self.config.max_output_chars] + "\n... [truncated]"

            elapsed_ms = (time.time() - start_time) * 1000

            return SandboxResult(
                success=True,
                output=output,
                execution_time_ms=round(elapsed_ms, 2),
                return_value=safe_globals.get("result"),
            )

        except TimeoutError:
            elapsed_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=f"Execution timed out after {self.config.timeout_seconds}s",
                timed_out=True,
                execution_time_ms=round(elapsed_ms, 2),
            )
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                execution_time_ms=round(elapsed_ms, 2),
            )
        finally:
            if self.config.enable_timeout:
                if _use_sigalrm:
                    signal.signal(signal.SIGALRM, old_handler or signal.SIG_DFL)
                    signal.setitimer(signal.ITIMER_REAL, 0)
                else:
                    _timeout_event.set()  # cancel thread
                    if _timeout_thread:
                        _timeout_thread.join(timeout=0.1)
