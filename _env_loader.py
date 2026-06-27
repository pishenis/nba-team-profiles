"""
Carregador de .env robusto e sem dependências externas.
Usado por todos os scripts do projeto para garantir que
BDL_API_KEY (e outras variáveis) sejam sempre encontradas,
com ou sem python-dotenv instalado.
"""

import os
from pathlib import Path


def load_env(env_path: str = ".env") -> None:
    """
    Carrega variáveis de um arquivo .env para os.environ,
    sem sobrescrever variáveis já definidas no shell.
    Não lança erro se o arquivo não existir.
    """
    path = Path(env_path)
    if not path.exists():
        return

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(*keys: str) -> dict:
    """
    Garante que cada chave em `keys` está definida (no .env ou no shell).
    Retorna um dict {chave: valor}. Sai do programa com mensagem clara
    se alguma estiver faltando.
    """
    load_env()
    result = {}
    missing = []
    for key in keys:
        value = os.environ.get(key, "")
        if not value:
            missing.append(key)
        result[key] = value

    if missing:
        print(f"\n❌ Faltam variáveis no .env: {', '.join(missing)}")
        print(f"   Verifique se o arquivo .env existe na pasta atual e contém:")
        for k in missing:
            print(f"   {k}=sua_chave_aqui")
        print()
        import sys
        sys.exit(1)

    return result
