import asyncio
import logging
import os
import time
import gc

# Attach to uvicorn's logger so output appears in PM2 logs automatically
logger = logging.getLogger("uvicorn.error")

last_request_time: float = time.time()
_monitor_task: asyncio.Task | None = None


def _get_timeout() -> int:
    """Read at call-time so .env changes take effect after restart."""
    return int(os.environ.get("IDLE_TIMEOUT_SECONDS", "60"))


def record_request():
    """Call this on every incoming chat request."""
    global last_request_time
    last_request_time = time.time()


def _offload_models():
    """Clear all lru_cache singletons to release RAM."""
    try:
        from app.rag.embeddings import get_embedder
        from app.rag.retriever import get_retriever
        from app.rag.reranker import get_reranker

        get_embedder.cache_clear()
        get_retriever.cache_clear()
        get_reranker.cache_clear()

        gc.collect()

        logger.info("[idle_manager] Models offloaded — RAM released.")
    except Exception as e:
        logger.error(f"[idle_manager] Offload failed: {e}")


async def _idle_monitor():
    """Background task — checks every 30s for inactivity."""
    offloaded = False
    timeout = _get_timeout()
    logger.info(f"[idle_manager] Monitor running — timeout={timeout}s, check interval=30s.")

    while True:
        await asyncio.sleep(30)                         # check every 30s (not 60)
        idle_seconds = time.time() - last_request_time
        timeout = _get_timeout()                        # re-read each cycle so env changes apply

        logger.info(
            f"[idle_manager] Idle check: {idle_seconds:.0f}s idle "
            f"(threshold={timeout}s, offloaded={offloaded})"
        )

        if idle_seconds >= timeout and not offloaded:
            logger.info(f"[idle_manager] Threshold reached — offloading models.")
            _offload_models()
            offloaded = True

        elif idle_seconds < timeout and offloaded:
            offloaded = False
            logger.info("[idle_manager] Traffic resumed — models reload on next request.")


def start_idle_monitor():
    global _monitor_task
    # get_running_loop() is correct here — we're called from inside async lifespan
    loop = asyncio.get_running_loop()
    _monitor_task = loop.create_task(_idle_monitor())
    logger.info(f"[idle_manager] Started — offload after {_get_timeout()}s inactivity.")


def stop_idle_monitor():
    global _monitor_task
    if _monitor_task:
        _monitor_task.cancel()
        logger.info("[idle_manager] Monitor stopped.")
        _monitor_task = None