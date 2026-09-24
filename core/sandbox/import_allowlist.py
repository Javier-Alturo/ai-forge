"""
CAPA 2: Allowlist de imports permitidos para código generado por LLM.
REGLA: Todo lo que no esté aquí está prohibido.
Para agregar un módulo nuevo, requiere aprobación manual en agents_config.json
"""

# Módulos explícitamente permitidos
ALLOWED_IMPORTS: set[str] = {
    # Stdlib seguros (solo lectura o sin efectos secundarios peligrosos)
    "os",           # Solo lectura — os.path, os.getcwd, os.listdir. Las ops de escritura/borrado son bloqueadas por ASTValidator.
    "pathlib",
    "json",
    "datetime",
    "time",
    "math",
    "re",
    "typing",
    "dataclasses",
    "collections",
    "itertools",
    "functools",
    "string",
    "textwrap",
    "hashlib",
    "base64",
    "uuid",
    "copy",
    "enum",
    "abc",
    "io",
    "random",
    "statistics",
    "decimal",
    "fractions",
    "calendar",
    "struct",
    "csv",
    "html",
    "urllib",

    # Terceros aprobados explícitamente
    "pydantic",
    "langchain",
    "langchain_core",
    "langchain_ollama",
    "chromadb",
    "requests",   # ⚠️ Solo para tools de HTTP explícitas, no por defecto
    "httpx",      # ⚠️ Idem

    # Científicos (para tools de análisis de datos)
    "pandas",
    "numpy",
    "matplotlib",
    "scipy",
    "sklearn",
}

# Módulos que NUNCA van a estar en la allowlist
EXPLICITLY_BANNED: set[str] = {
    "subprocess", "multiprocessing", "threading",  # fork/spawn
    "ctypes", "cffi",                               # acceso nativo
    "socket", "socketserver",                       # red raw
    "pty", "termios", "tty",                        # terminal
    "pickle", "shelve",                             # deserialización insegura
    "importlib",                                    # importación dinámica
    "builtins",                                     # bypass de restricciones
    "gc",                                           # control de GC
    "sys",                                          # sys.exit, sys.modules
    "signal",                                       # manejo de señales del OS
    "resource",                                     # límites del OS
    "mmap",                                         # memoria compartida
    "winreg",                                       # registro de Windows
    "winsound",                                     # audio del sistema
    "msvcrt",                                       # C runtime de Windows
}
