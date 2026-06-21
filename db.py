import os
from typing import Any, Dict, Optional, Tuple

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL")
db_pool: Optional[asyncpg.Pool] = None


async def init_database() -> asyncpg.Pool:
    """
    Inicializa el pool de conexiones y crea los esquemas necesarios.
    """
    global db_pool
    if db_pool:
        return db_pool

    if not DATABASE_URL:
        raise RuntimeError("No se encontró DATABASE_URL en el entorno")

    db_pool = await asyncpg.create_pool(DATABASE_URL, max_size=10)
    await _ensure_schema(db_pool)
    return db_pool


async def close_database() -> None:
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


async def _ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS frames (
                id BIGSERIAL PRIMARY KEY,
                received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                peer_ip TEXT,
                peer_port INTEGER,
                raw_hex TEXT,
                raw_bytes BYTEA,
                ascii_text TEXT,
                frame_length INTEGER,
                protocolo_id TEXT,
                tipo TEXT,
                imei TEXT,
                parsed JSONB
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                imei TEXT PRIMARY KEY,
                last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_frame_id BIGINT REFERENCES frames(id)
            );
            """
        )


async def registrar_trama(
    pool: asyncpg.Pool,
    direccion: Optional[Tuple[str, int]],
    datos: bytes,
    info: Dict[str, Any],
) -> int:
    """
    Inserta la trama y actualiza la última vez que se vio cada IMEI.
    """
    peer_ip = None
    peer_port = None
    if direccion:
        try:
            peer_ip, peer_port = direccion
        except (TypeError, ValueError):
            pass

    raw_hex = datos.hex().upper()
    ascii_text = datos.decode("ascii", errors="replace")
    frame_length = len(datos)
    protocolo_id = info.get("protocolo_id")
    tipo = info.get("tipo")
    imei = info.get("imei")

    async with pool.acquire() as conn:
        frame_id = await conn.fetchval(
            """
            INSERT INTO frames (
                peer_ip,
                peer_port,
                raw_hex,
                raw_bytes,
                ascii_text,
                frame_length,
                protocolo_id,
                tipo,
                imei,
                parsed
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING id
            """,
            peer_ip,
            peer_port,
            raw_hex,
            datos,
            ascii_text,
            frame_length,
            protocolo_id,
            tipo,
            imei,
            info,
        )

        if imei:
            await conn.execute(
                """
                INSERT INTO devices (imei, last_seen, last_frame_id)
                VALUES ($1, NOW(), $2)
                ON CONFLICT (imei) DO UPDATE
                    SET last_seen = NOW(),
                        last_frame_id = EXCLUDED.last_frame_id
                """,
                imei,
                frame_id,
            )

    return frame_id
