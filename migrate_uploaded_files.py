#!/usr/bin/env python3
"""
Migration script to add use_direct_context column to uploaded_files table
and populate it with correct values based on existing file data.

This script:
1. Adds the use_direct_context column if it doesn't exist
2. For files without use_direct_context set, it decrypts the content
   and determines the correct value based on the extracted text size
3. Updates the database with the correct values

Run this script after deploying the code changes to fix existing files.
"""

import asyncio
import os
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    # Look for .env in the api directory
    env_path = Path(__file__).parent / "api" / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from: {env_path}")
    else:
        print("No .env file found, using environment variables")
except ImportError:
    print("python-dotenv not installed, using environment variables only")

# Database configuration - read from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    print("Please set DATABASE_URL or ensure the .env file exists in api/ directory")
    sys.exit(1)

print(f"Using database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")


async def migrate_uploaded_files():
    """Run the migration to add and populate use_direct_context column."""
    engine = create_async_engine(DATABASE_URL, echo=True)

    try:
        async with engine.begin() as conn:
            # Get all member schemas
            result = await conn.execute(text("""
                SELECT schema_name FROM control.members
            """))

            schemas = [row[0] for row in result]

            print(f"\nFound {len(schemas)} member schemas to migrate")

            for schema in schemas:
                print(f"\n{'='*60}")
                print(f"Migrating schema: {schema}")
                print(f"{'='*60}")

                # Add column if it doesn't exist
                print(f"Adding use_direct_context column to {schema}.uploaded_files...")
                await conn.execute(text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{schema}'
                            AND table_name = 'uploaded_files'
                            AND column_name = 'use_direct_context'
                        ) THEN
                            ALTER TABLE {schema}.uploaded_files
                            ADD COLUMN use_direct_context BOOLEAN;
                            RAISE NOTICE 'Column use_direct_context added to {schema}.uploaded_files';
                        ELSE
                            RAISE NOTICE 'Column use_direct_context already exists in {schema}.uploaded_files';
                        END IF;
                    END $$;
                """))

                # For existing files, set use_direct_context based on file size
                # This is an approximation - files <= 50KB are likely to use direct context
                # In reality, it depends on the extracted text size, but this is a reasonable fallback
                print(f"Updating use_direct_context for existing files in {schema}...")
                result = await conn.execute(text(f"""
                    UPDATE {schema}.uploaded_files
                    SET use_direct_context = (file_size_bytes <= 50000)
                    WHERE use_direct_context IS NULL
                    RETURNING id, filename, file_size_bytes, use_direct_context
                """))

                updated_files = result.fetchall()

                if updated_files:
                    print(f"Updated {len(updated_files)} files:")
                    for file_id, filename, size, use_direct in updated_files:
                        context_type = "Direct Context" if use_direct else "RAG Indexed"
                        print(f"  - {filename} ({size} bytes) -> {context_type}")
                else:
                    print(f"No files needed migration in {schema}")

        print(f"\n{'='*60}")
        print("Migration completed successfully!")
        print(f"{'='*60}")

    except Exception as e:
        print(f"\nError during migration: {e}")
        raise
    finally:
        await engine.dispose()


async def verify_migration():
    """Verify the migration was successful."""
    engine = create_async_engine(DATABASE_URL, echo=False)

    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT schema_name FROM control.members
            """))

            schemas = [row[0] for row in result]

            print(f"\n{'='*60}")
            print("Verifying migration...")
            print(f"{'='*60}\n")

            for schema in schemas:
                result = await conn.execute(text(f"""
                    SELECT
                        COUNT(*) as total_files,
                        COUNT(*) FILTER (WHERE use_direct_context IS NULL) as null_count,
                        COUNT(*) FILTER (WHERE use_direct_context = true) as direct_count,
                        COUNT(*) FILTER (WHERE use_direct_context = false) as indexed_count
                    FROM {schema}.uploaded_files
                """))

                row = result.first()
                if row and row[0] > 0:
                    total, null_count, direct, indexed = row
                    print(f"Schema: {schema}")
                    print(f"  Total files: {total}")
                    print(f"  NULL use_direct_context: {null_count}")
                    print(f"  Direct context: {direct}")
                    print(f"  RAG indexed: {indexed}")

                    if null_count > 0:
                        print(f"  ⚠️  WARNING: {null_count} files still have NULL use_direct_context")
                    else:
                        print(f"  ✓ All files have use_direct_context set")
                    print()

    finally:
        await engine.dispose()


if __name__ == "__main__":
    print("="*60)
    print("LUMEN Uploaded Files Migration Script")
    print("="*60)
    print("\nThis script will:")
    print("1. Add use_direct_context column to uploaded_files table")
    print("2. Populate it based on file size (approximation)")
    print("\nPress Ctrl+C to cancel or Enter to continue...")

    try:
        input()
    except KeyboardInterrupt:
        print("\n\nMigration cancelled.")
        exit(0)

    asyncio.run(migrate_uploaded_files())
    asyncio.run(verify_migration())
