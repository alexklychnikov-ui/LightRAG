from pathlib import Path
import secrets


env_path = Path("/opt/LightRAG/.env")
text = env_path.read_text(encoding="utf-8")
lines = text.splitlines()

updates = {
    "LIGHTRAG_KV_STORAGE": "PGKVStorage",
    "LIGHTRAG_DOC_STATUS_STORAGE": "PGDocStatusStorage",
    "LIGHTRAG_GRAPH_STORAGE": "PGGraphStorage",
    "LIGHTRAG_VECTOR_STORAGE": "PGVectorStorage",
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "lightrag",
    "POSTGRES_DATABASE": "lightrag",
    "POSTGRES_MAX_CONNECTIONS": "25",
    "POSTGRES_VECTOR_INDEX_TYPE": "HNSW",
    "POSTGRES_HNSW_M": "16",
    "POSTGRES_HNSW_EF": "200",
}

if not any(line.startswith("POSTGRES_PASSWORD=") for line in lines):
    lines.append(f"POSTGRES_PASSWORD={secrets.token_hex(16)}")

idx = {}
for i, line in enumerate(lines):
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        idx[key] = i

for key, value in updates.items():
    row = f"{key}={value}"
    if key in idx:
        lines[idx[key]] = row
    else:
        lines.append(row)

env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("PG_ENV_UPDATED")
