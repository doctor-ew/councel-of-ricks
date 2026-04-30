"""Document ingestion service."""

import logging
from pathlib import Path

from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Chunk, Document
from app.schemas.documents import IngestResponse

logger = logging.getLogger(__name__)
settings = get_settings()


class IngestionService:
    """Service for ingesting transcript documents into the vector store."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embed_model = OpenAIEmbedding(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        self.splitter = SentenceSplitter(
            chunk_size=512,
            chunk_overlap=50,
        )

    async def ingest_directory(self, directory_path: str | None = None) -> IngestResponse:
        """Recursively ingest all .txt transcript files in a directory."""
        path = Path(directory_path or settings.documents_path)

        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        txt_files = list(path.rglob("*.txt"))
        logger.info(f"Found {len(txt_files)} transcript files to ingest")

        documents_ingested = 0
        total_chunks = 0
        errors: list[str] = []

        for txt_path in txt_files:
            try:
                doc_id, chunk_count = await self._ingest_txt(txt_path)
                documents_ingested += 1
                total_chunks += chunk_count
                logger.info(f"Ingested {txt_path.name}: {chunk_count} chunks")
            except Exception as e:
                error_msg = f"Failed to ingest {txt_path.name}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return IngestResponse(
            documents_ingested=documents_ingested,
            total_chunks=total_chunks,
            errors=errors,
        )

    async def _ingest_txt(self, txt_path: Path) -> tuple[str, int]:
        """Ingest a single .txt transcript file."""
        raw = txt_path.read_text(encoding="utf-8")
        text = self._sanitize_text(raw)

        document = Document(
            filename=txt_path.name,
            file_path=str(txt_path),
            document_type="episode",
            total_pages=None,
            deponent_name=None,
            metadata_={"source_directory": str(txt_path.parent.name)},
        )
        self.db.add(document)
        await self.db.flush()

        chunks = self.splitter.split_text(text)
        chunk_count = 0

        for idx, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue

            embedding = await self._get_embedding(chunk_text)

            chunk = Chunk(
                document_id=document.id,
                page_number=1,  # no page concept in .txt transcripts
                chunk_index=idx,
                content=chunk_text,
                embedding=embedding,
                metadata_={
                    "filename": txt_path.name,
                    "chunk_index": idx,
                },
            )
            self.db.add(chunk)
            chunk_count += 1

        await self.db.flush()
        return str(document.id), chunk_count

    def _sanitize_text(self, text: str) -> str:
        """Remove null bytes and control characters unsafe for PostgreSQL."""
        text = text.replace("\x00", "")
        text = "".join(char for char in text if char == "\n" or char == "\t" or not (0 <= ord(char) < 32))
        return text

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return self.embed_model.get_text_embedding(text)
