"""Buy or Wait financial decision agent package."""

# Expose standard library `code` module attributes for compatibility with pdb/pytest
try:
    import sys
    import os
    import importlib.util
    for _p in sys.path:
        _cand = os.path.join(_p, "code.py")
        if os.path.exists(_cand):
            _spec = importlib.util.spec_from_file_location("_stdlib_code", _cand)
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            for _attr in ["InteractiveConsole", "InteractiveInterpreter", "compile_command", "interact", "CommandCompiler"]:
                if hasattr(_mod, _attr):
                    globals()[_attr] = getattr(_mod, _attr)
            break
except Exception:
    pass
