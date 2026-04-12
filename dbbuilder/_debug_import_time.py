"""Debug: measure import times for heavy modules."""
import time

t0 = time.time()
import db_builder.config
t1 = time.time()
print(f"config:     {t1-t0:.3f}s")

from db_builder.database import DatabaseManager
t2 = time.time()
print(f"database:   {t2-t1:.3f}s")

from db_builder.filetype import detect_mime
t3 = time.time()
print(f"filetype:   {t3-t2:.3f}s")

from db_builder.chunking.base import SemanticChunker, count_tokens
t4 = time.time()
print(f"chunking:   {t4-t3:.3f}s")

# tiktoken first call
_ = count_tokens("test")
t5 = time.time()
print(f"tiktoken 1st call: {t5-t4:.3f}s")

from db_builder.enrichment import LLMEnricher
t6 = time.time()
print(f"enrichment: {t6-t5:.3f}s")

from db_builder.embedding.client import EmbeddingClient
t7 = time.time()
print(f"embed client: {t7-t6:.3f}s")

from db_builder.store.chromadb_writer import ChromaDBWriter
t8 = time.time()
print(f"chromadb:   {t8-t7:.3f}s")

import chromadb
t9 = time.time()
print(f"chromadb init: {t9-t8:.3f}s")

# PySide6
from PySide6.QtWidgets import QApplication
t10 = time.time()
print(f"PySide6:    {t10-t9:.3f}s")

print(f"\nTOTAL imports: {t10-t0:.3f}s")
