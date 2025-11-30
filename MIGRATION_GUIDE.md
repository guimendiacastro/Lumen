# Document Indexing Issue - Fix and Migration Guide

## Problem Summary

When loading old conversations with uploaded files, some files were showing "Indexing..." status even though they were already indexed successfully. This is a **backend issue** caused by a mismatch in how the system determines whether a file should use "direct context" vs "RAG indexing".

### Root Cause

The issue occurs in [api/app/routers/files.py:219](api/app/routers/files.py#L219) where the listing logic uses:

```python
use_direct = row[3] <= 50000  # Approximate - based on file_size_bytes
```

However, during upload, the decision is made based on **extracted text character count** (≤ 50,000 chars), not the original file size in bytes. This creates a mismatch:

- **Upload time**: Decision based on extracted text size (characters)
- **Listing time**: Decision based on file size (bytes)

Example scenarios that cause the bug:
- A 200KB PDF extracts to 40K characters → uses direct context, but listing thinks it should be indexed
- A 45KB text file extracts to 60K characters → gets indexed, but listing thinks it's direct context

When the listing incorrectly determines a file should be indexed but it wasn't, Azure AI Search returns 0 chunks, and the frontend displays "Indexing...".

## Solution

Store the `use_direct_context` decision in the database during upload, so we don't need to approximate it during listing.

### Changes Made

#### 1. Database Schema Changes

**File**: [api/app/routers/bootstrap.py](api/app/routers/bootstrap.py)

Added `use_direct_context BOOLEAN` column to the `uploaded_files` table.

#### 2. Upload Logic

**File**: [api/app/routers/files.py:110-133](api/app/routers/files.py#L110-L133)

Updated the INSERT statement to include `use_direct_context` when creating new file records.

#### 3. File Listing Logic

**File**: [api/app/routers/files.py:201-220](api/app/routers/files.py#L201-L220)

Updated the SELECT statement to retrieve `use_direct_context` from the database instead of approximating it.

#### 4. Retry Indexing Logic

**File**: [api/app/routers/files.py:407-455](api/app/routers/files.py#L407-L455)

Updated to read `use_direct_context` from the database when retrying failed indexing.

#### 5. Test Schema

**File**: [api/tests/conftest.py:193-208](api/tests/conftest.py#L193-L208)

Updated test database schema to include the new column.

#### 6. Migration Endpoint

**File**: [api/app/routers/bootstrap.py:188-222](api/app/routers/bootstrap.py#L188-L222)

Added `POST /bootstrap/migrate-uploaded-files` endpoint for updating existing databases.

## Migration Steps

### Option 1: Using the Migration Endpoint (Recommended for Development)

1. Deploy the updated code
2. Make a POST request to the migration endpoint:

```bash
curl -X POST "http://localhost:8000/bootstrap/migrate-uploaded-files" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

This will:
- Add the `use_direct_context` column if it doesn't exist
- Keep existing files working with a fallback approximation

### Option 2: Using the Migration Script (Recommended for Production)

1. Deploy the updated code

2. Run the migration script:

```bash
cd /Users/gui/Desktop/lumen/lumen
python migrate_uploaded_files.py
```

This script will:
- Add the column to all member schemas
- Update existing files with approximated values based on file size
- Verify the migration completed successfully

### Option 3: Manual SQL Migration

If you prefer to run SQL directly:

```sql
-- For each member schema, run:
ALTER TABLE your_schema_name.uploaded_files
ADD COLUMN IF NOT EXISTS use_direct_context BOOLEAN;

-- Update existing files (approximation based on size)
UPDATE your_schema_name.uploaded_files
SET use_direct_context = (file_size_bytes <= 50000)
WHERE use_direct_context IS NULL;
```

## Testing the Fix

After migration:

1. **New uploads**: Files will have `use_direct_context` correctly set based on extracted text size

2. **Existing files**: Will use the approximated value or fallback logic:
   ```python
   use_direct = row[7] if row[7] is not None else (row[3] <= 50000)
   ```

3. **Loading old conversations**: Files should now display correct status:
   - "Direct Context" badge for small files
   - "Indexed (N chunks)" for successfully indexed files
   - Only show "Indexing..." for files actually being indexed

## Verification

To verify the fix is working:

1. **Check database**:
   ```sql
   SELECT id, filename, file_size_bytes, use_direct_context, status
   FROM your_schema.uploaded_files
   LIMIT 10;
   ```

2. **Upload a new file** and verify it gets `use_direct_context` set correctly

3. **Load an old conversation** and verify files display correct status

4. **Check backend logs** for any errors related to file indexing status

## Backward Compatibility

The fix maintains backward compatibility:

- **New files**: Will always have `use_direct_context` set correctly
- **Old files**: Use fallback approximation if column is NULL
- **Existing code**: Works with or without the new column (uses approximation as fallback)

## Notes

- The migration is **idempotent** - safe to run multiple times
- The fallback logic ensures the system works even for old records without the column
- New uploads will always have the correct value, so the issue won't occur for new files
- For maximum accuracy, consider re-uploading files that are frequently accessed if they show incorrect status

## Related Files

- [api/app/routers/files.py](api/app/routers/files.py) - File upload and listing logic
- [api/app/routers/bootstrap.py](api/app/routers/bootstrap.py) - Schema and migration
- [api/tests/conftest.py](api/tests/conftest.py) - Test database schema
- [migrate_uploaded_files.py](migrate_uploaded_files.py) - Migration script
- [web/src/components/FileUpload.tsx](web/src/components/FileUpload.tsx) - Frontend file display (no changes needed)

## Support

If you encounter issues:

1. Check that the database migration completed successfully
2. Verify the `use_direct_context` column exists in your schema
3. Check backend logs for any errors during file listing
4. Test with a fresh file upload to verify the fix is working for new files
