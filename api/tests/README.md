# LUMEN API Test Suite

Comprehensive test suite for the LUMEN API with full coverage of routers, services, and utilities.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Setup](#setup)
- [Running Tests](#running-tests)
- [Test Coverage](#test-coverage)
- [Writing Tests](#writing-tests)
- [Fixtures](#fixtures)
- [Troubleshooting](#troubleshooting)

## Overview

This test suite provides comprehensive coverage of the LUMEN API including:

- **Router Tests**: All API endpoints (documents, threads, files, AI, bootstrap, health)
- **Service Tests**: File processing, RAG service
- **Utility Tests**: Document validation, edit commands, sanitization
- **Integration Tests**: End-to-end workflows with database and encryption

### Test Statistics

- **Total Test Files**: 10+
- **Test Classes**: 60+
- **Test Cases**: 200+
- **Target Coverage**: 70%+

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_routers/            # API endpoint tests
│   ├── test_bootstrap.py    # Schema bootstrap tests
│   ├── test_documents.py    # Document CRUD tests
│   ├── test_threads.py      # Chat thread tests
│   ├── test_files.py        # File upload tests
│   ├── test_ai.py           # AI comparison tests
│   └── test_health.py       # Health check tests
├── test_services/           # Service layer tests
│   ├── test_file_processor.py
│   └── test_rag_service.py
└── test_utils/              # Utility function tests
    └── test_validation.py
```

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ (for test database)
- Qdrant (optional, for RAG service tests)
- Vault (optional, mocked in tests)

### Installation

1. **Install dependencies**:
   ```bash
   cd /home/user/Lumen/api
   pip install -r requirements.txt
   ```

2. **Set up test database**:
   ```bash
   # Create test database
   createdb lumen_test

   # Or using psql
   psql -U postgres -c "CREATE DATABASE lumen_test;"
   ```

3. **Configure environment variables**:
   ```bash
   # Create .env.test file
   cat > .env.test << EOF
   TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lumen_test
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/lumen_test

   # Mock Vault (will be mocked in tests)
   VAULT_ADDR=http://localhost:8200
   VAULT_TOKEN=test_token

   # Optional: Real Qdrant for RAG tests
   QDRANT_HOST=localhost
   QDRANT_PORT=6333

   # Dev mode
   DEV_FAKE_AUTH=true
   DEV_FAKE_USER_ID=test_user_01
   DEV_FAKE_ORG_ID=test_org_01
   EOF
   ```

## Running Tests

### Run All Tests

```bash
cd /home/user/Lumen/api
pytest
```

### Run Specific Test Files

```bash
# Run router tests only
pytest tests/test_routers/

# Run specific test file
pytest tests/test_routers/test_documents.py

# Run specific test class
pytest tests/test_routers/test_documents.py::TestDocumentCreation

# Run specific test
pytest tests/test_routers/test_documents.py::TestDocumentCreation::test_create_document_success
```

### Run with Coverage

```bash
# Generate coverage report
pytest --cov=app --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run with Markers

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only database tests
pytest -m database

# Skip slow tests
pytest -m "not slow"
```

### Verbose Output

```bash
# Verbose output with test names
pytest -v

# Very verbose with all output
pytest -vv

# Show print statements
pytest -s

# Show local variables on failure
pytest -l
```

### Parallel Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel
pytest -n auto
```

## Test Coverage

### Current Coverage by Module

| Module | Coverage | Test File |
|--------|----------|-----------|
| routers/bootstrap.py | 95%+ | test_routers/test_bootstrap.py |
| routers/documents.py | 90%+ | test_routers/test_documents.py |
| routers/threads.py | 90%+ | test_routers/test_threads.py |
| routers/files.py | 85%+ | test_routers/test_files.py |
| routers/ai.py | 75%+ | test_routers/test_ai.py |
| routers/health.py | 100% | test_routers/test_health.py |
| services/file_processor.py | 95%+ | test_services/test_file_processor.py |
| utils/validation.py | 90%+ | test_utils/test_validation.py |

### Viewing Coverage

```bash
# Generate and view coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Coverage Goals

- **Overall**: 70%+ coverage
- **Critical paths**: 90%+ coverage (auth, encryption, data persistence)
- **Utility functions**: 85%+ coverage
- **Error handling**: All error paths tested

## Writing Tests

### Test Template

```python
"""
Tests for [module name].

Brief description of what this module tests.
"""

import pytest
from httpx import AsyncClient


class TestFeature:
    """Tests for specific feature."""

    @pytest.mark.asyncio
    async def test_feature_success(self, async_client: AsyncClient):
        """Should [expected behavior] when [condition]."""
        # Arrange
        payload = {"key": "value"}

        # Act
        response = await async_client.post("/endpoint", json=payload)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "value"
```

### Best Practices

1. **Use descriptive test names**:
   - Pattern: `test_<function>_<scenario>_<expected_outcome>`
   - Example: `test_create_document_with_empty_title_fails`

2. **Follow AAA pattern**:
   - **Arrange**: Set up test data and prerequisites
   - **Act**: Execute the code under test
   - **Assert**: Verify the expected outcomes

3. **Use fixtures for common setup**:
   ```python
   @pytest.mark.asyncio
   async def test_something(
       self,
       async_client: AsyncClient,
       create_test_document,
       mock_vault
   ):
       doc_id = await create_test_document()
       # ... test code
   ```

4. **Test both success and failure paths**:
   - Happy path (valid inputs, expected success)
   - Validation errors (invalid inputs, missing fields)
   - Not found scenarios (non-existent resources)
   - Edge cases (boundary conditions, special characters)

5. **Verify database state changes**:
   ```python
   # After creating resource
   result = await db_session.execute(
       text("SELECT * FROM table WHERE id = :id"),
       {"id": resource_id}
   )
   row = result.first()
   assert row is not None
   ```

6. **Use parametrize for multiple scenarios**:
   ```python
   @pytest.mark.parametrize("payload,expected_error", [
       ({"title": ""}, "title"),
       ({}, "title"),
       ({"title": "x" * 1001}, "title"),
   ])
   @pytest.mark.asyncio
   async def test_validation_errors(self, async_client, payload, expected_error):
       response = await async_client.post("/endpoint", json=payload)
       assert response.status_code == 422
   ```

## Fixtures

### Database Fixtures

- **test_engine** (session): Test database engine with schema setup
- **db_session** (function, autouse): Database session with transaction rollback
- **create_test_document**: Factory fixture to create test documents
- **create_test_thread**: Factory fixture to create test threads
- **create_test_message**: Factory fixture to create test messages

### HTTP Client Fixtures

- **async_client**: Async HTTP client for testing endpoints
- **test_identity**: Test user identity
- **override_get_identity**: Override authentication dependency

### Mocking Fixtures

- **mock_vault**: Mocks Vault encryption/decryption
- **mock_rag_service**: Mocks RAG service for file indexing
- **mock_get_rag_service**: Mocks get_rag_service function
- **mock_llm_clients**: Mocks LLM provider responses
- **mock_file_processor**: Mocks file processing

### Example Usage

```python
@pytest.mark.asyncio
async def test_example(
    async_client: AsyncClient,
    create_test_document,
    mock_vault
):
    # Create test document
    doc_id = await create_test_document(
        title="Test Doc",
        content="Test content"
    )

    # Make request
    response = await async_client.get(f"/documents/{doc_id}")

    # Verify
    assert response.status_code == 200
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

**Problem**: `asyncpg.exceptions.InvalidCatalogNameError: database "lumen_test" does not exist`

**Solution**:
```bash
createdb lumen_test
```

#### 2. Test Schema Not Found

**Problem**: `relation "documents" does not exist`

**Solution**: The test_engine fixture automatically creates the schema. Ensure you're using the `db_session` fixture (autouse).

#### 3. Vault Mock Not Working

**Problem**: Tests failing with Vault connection errors

**Solution**: Ensure `mock_vault` fixture is included:
```python
async def test_example(self, async_client, mock_vault):
    # mock_vault fixture patches encrypt/decrypt
```

#### 4. Async Warnings

**Problem**: `RuntimeWarning: coroutine was never awaited`

**Solution**: Ensure all async functions are awaited:
```python
# Wrong
result = create_test_document()

# Correct
result = await create_test_document()
```

#### 5. Import Errors

**Problem**: `ModuleNotFoundError: No module named 'app'`

**Solution**: Run pytest from the api directory:
```bash
cd /home/user/Lumen/api
pytest
```

### Debug Mode

Run tests with debugging enabled:

```bash
# Show all output
pytest -s -vv

# Drop into debugger on failure
pytest --pdb

# Drop into debugger on first failure
pytest -x --pdb
```

### Test Isolation Issues

If tests are interfering with each other:

1. **Check transaction rollback**: Ensure `db_session` fixture is being used
2. **Check fixture scope**: Most fixtures should be function-scoped
3. **Run tests individually** to identify the problem:
   ```bash
   pytest tests/test_file.py::test_specific -vv
   ```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: lumen_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run tests
        run: |
          pytest --cov=app --cov-report=xml
        env:
          TEST_DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/lumen_test

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [HTTPX Documentation](https://www.python-httpx.org/)
- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

## Contributing

When adding new features to the API:

1. **Write tests first** (TDD approach recommended)
2. **Maintain coverage** above 70%
3. **Follow naming conventions** for test files and functions
4. **Document complex test scenarios** with comments
5. **Update this README** if adding new test patterns or fixtures

## Support

For issues or questions about the test suite:

1. Check the troubleshooting section above
2. Review existing test files for examples
3. Open an issue in the project repository
