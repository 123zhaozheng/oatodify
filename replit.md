# OA Document Processing System

## Overview

This is an OA (Office Automation) document processing system that automatically downloads, decrypts, analyzes, and integrates documents into a Dify knowledge base. The system consists of a FastAPI backend for document processing, a Streamlit frontend for monitoring and management, and Celery for asynchronous task processing.

The system handles encrypted OA documents by downloading them from S3 storage, decrypting them using custom algorithms, parsing various document formats, analyzing content with AI, and finally integrating approved documents into a knowledge management system.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Web Framework Architecture
- **Backend**: FastAPI with SQLAlchemy ORM for REST API services
- **Frontend**: Streamlit for web-based dashboard and management interface
- **Database**: PostgreSQL with SQLAlchemy models for document metadata and processing logs
- **Task Queue**: Celery with Redis broker for asynchronous document processing

### Document Processing Pipeline
The system follows a multi-stage pipeline:
1. **Download Stage**: Fetches encrypted documents from S3 storage
2. **Decryption Stage**: Uses AES decryption with custom key generation
3. **Parsing Stage**: Extracts content from various document formats (PDF, DOCX, DOC, TXT)
4. **AI Analysis Stage**: Analyzes document relevance using OpenAI GPT models
5. **Approval Stage**: Routes low-confidence documents for human review
6. **Integration Stage**: Adds approved documents to Dify knowledge base

### Data Models
Core entities include:
- **OAFileInfo**: Stores document metadata, processing status, and business categorization
- **ProcessingLog**: Tracks detailed processing steps and outcomes
- **Business Categories**: Classifies documents (contract, report, notice, policy, other)
- **Processing Status**: Tracks workflow state (pending, downloading, decrypting, parsing, analyzing, awaiting_approval, completed, failed)

### Configuration Management
Uses Pydantic Settings for environment-based configuration with support for:
- Database connections
- S3 storage credentials
- OpenAI API keys
- Dify integration settings
- Redis queue configuration
- File processing limits and supported formats

### Service Layer Architecture
Modular services for specific functionalities:
- **S3Service**: Handles file downloads from S3-compatible storage
- **DecryptionService**: Implements custom AES decryption for OA documents
- **DocumentParser**: Multi-format document content extraction
- **AIAnalyzer**: OpenAI-powered content analysis and relevance scoring
- **DifyService**: Knowledge base integration and document ingestion

## External Dependencies

### Storage and Infrastructure
- **S3-Compatible Storage**: Document storage with configurable endpoints
- **PostgreSQL**: Primary database for metadata and processing logs
- **Redis**: Message broker for Celery task queue

### AI and ML Services
- **OpenAI GPT**: Document content analysis and relevance scoring
- **Dify Platform**: Knowledge base management and document integration

### Document Processing Libraries
- **python-magic**: File type detection and validation
- **PyCryptodome**: AES decryption implementation
- **PyPDF2/pdfplumber**: PDF content extraction
- **python-docx**: Microsoft Word document parsing
- **Beautiful Soup**: HTML/XML content extraction

### Web Framework Dependencies
- **FastAPI**: REST API framework with automatic OpenAPI documentation
- **Streamlit**: Interactive web dashboard for monitoring and management
- **Celery**: Distributed task queue for asynchronous processing
- **SQLAlchemy**: Database ORM with migration support
- **Uvicorn**: ASGI server for FastAPI application

### Monitoring and Utilities
- **Plotly**: Interactive charts and visualizations for dashboard
- **Pandas**: Data manipulation for reporting and analytics
- **Requests**: HTTP client for external API integrations
- **Pydantic**: Data validation and settings management