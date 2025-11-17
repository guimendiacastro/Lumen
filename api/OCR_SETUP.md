# OCR Setup Guide - Azure Document Intelligence

This guide explains how to set up OCR (Optical Character Recognition) for automatic text extraction from scanned PDFs in LUMEN.

## Overview

LUMEN now supports automatic OCR for scanned PDF documents using Azure Document Intelligence (formerly Form Recognizer). The system intelligently detects whether a PDF needs OCR and processes it accordingly.

### How It Works

1. **User uploads a PDF** through the `/files/upload` endpoint
2. **PyPDF2 attempts text extraction** (fast, works for text-based PDFs)
3. **System checks text quality**:
   - If average characters per page < 50 → Likely scanned, triggers OCR
   - If average characters per page ≥ 50 → Has text layer, uses PyPDF2 result
4. **OCR processing** (if needed):
   - Sends PDF to Azure Document Intelligence
   - Extracts text with multi-language support (60+ languages)
   - Preserves document structure and layout
5. **Text is chunked and indexed** in Azure AI Search for RAG

### Benefits

- **Automatic detection**: No manual intervention needed
- **Multi-language support**: Works with 60+ languages out of the box
- **High accuracy**: Azure Document Intelligence provides industry-leading OCR
- **Seamless integration**: Works with existing RAG pipeline
- **Graceful fallback**: If OCR is not configured, returns PyPDF2 text with warning

## Setup Instructions

### 1. Create Azure Document Intelligence Resource

1. Go to the [Azure Portal](https://portal.azure.com)
2. Click **Create a resource**
3. Search for **"Document Intelligence"** (or "Form Recognizer")
4. Click **Create**
5. Configure:
   - **Subscription**: Select your subscription
   - **Resource Group**: Use existing or create new
   - **Region**: Choose closest to your users (e.g., East US, West Europe)
   - **Name**: e.g., `lumen-document-intelligence`
   - **Pricing Tier**:
     - **Free (F0)**: 500 pages/month free (good for testing)
     - **Standard (S0)**: $1.50 per 1,000 pages (production)
6. Click **Review + Create** → **Create**
7. Wait for deployment to complete

### 2. Get Your Credentials

1. Go to your Document Intelligence resource
2. Navigate to **Keys and Endpoint** (left sidebar)
3. Copy:
   - **Endpoint**: `https://your-resource.cognitiveservices.azure.com`
   - **Key 1** or **Key 2**: Your API key

### 3. Configure Environment Variables

Add the following to your `.env` file:

```bash
# Azure Document Intelligence (OCR) Configuration
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-resource.cognitiveservices.azure.com
AZURE_DOCUMENT_INTELLIGENCE_KEY=your_api_key_here
```

Replace:
- `your-resource` with your actual resource name
- `your_api_key_here` with the key from step 2

### 4. Restart Your Application

```bash
# If using Docker
docker-compose restart api

# If running locally
# Stop the FastAPI server and restart it
```

## Verification

### Check OCR Configuration

The system will log whether OCR is available at startup. Look for logs like:

```
INFO: OCR is properly configured and available
```

Or warnings if not configured:

```
WARNING: OCR is needed but Azure Document Intelligence is not configured
```

### Test with a Scanned PDF

1. Upload a scanned PDF through the LUMEN interface
2. Check the logs for OCR activity:

```
INFO: PDF appears to be scanned (avg 12.3 chars/page). Attempting OCR extraction...
INFO: Starting Azure Document Intelligence OCR processing
INFO: OCR extraction completed. Pages: 5, Characters: 2847
INFO: OCR extraction successful. Extracted 2847 characters from 5 pages.
```

### Test with a Text-Based PDF

1. Upload a normal PDF with selectable text
2. Check logs to verify PyPDF2 is used (faster):

```
INFO: PDF has sufficient text (avg 1847.2 chars/page). Using PyPDF2 extraction.
```

## Pricing

### Azure Document Intelligence Pricing

| Tier | Price | Features |
|------|-------|----------|
| **Free (F0)** | Free | 500 pages/month |
| **Standard (S0)** | $1.50 per 1,000 pages | Unlimited pages |

### Example Costs

- **Small organization** (100 scanned PDFs/month, avg 10 pages each) = 1,000 pages = **$1.50/month**
- **Medium organization** (1,000 scanned PDFs/month, avg 10 pages each) = 10,000 pages = **$15/month**
- **Large organization** (10,000 scanned PDFs/month, avg 10 pages each) = 100,000 pages = **$150/month**

Note: Text-based PDFs don't use OCR, so they don't incur costs.

## Language Support

Azure Document Intelligence supports 60+ languages including:

- **Western European**: English, Spanish, French, German, Italian, Portuguese, Dutch, etc.
- **Eastern European**: Polish, Czech, Hungarian, Romanian, Russian, Ukrainian, etc.
- **Asian**: Chinese (Simplified & Traditional), Japanese, Korean, Thai, Vietnamese, etc.
- **Middle Eastern**: Arabic, Hebrew
- **Others**: Hindi, Turkish, Greek, and more

Full list: [Azure Document Intelligence Language Support](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support)

## Troubleshooting

### OCR Not Working

**Symptom**: Scanned PDFs return empty or minimal text

**Solutions**:
1. Check environment variables are set correctly
2. Verify credentials in Azure Portal
3. Check API key has not expired
4. Review application logs for error messages
5. Ensure firewall/network allows access to `*.cognitiveservices.azure.com`

### OCR Too Slow

**Symptom**: File upload takes too long

**Solutions**:
1. Check Azure resource region (closer is faster)
2. Upgrade to higher pricing tier if on Free tier
3. Consider reducing PDF file sizes before upload
4. Check network latency to Azure

### OCR Errors

**Symptom**: Error messages in logs

**Common errors**:

1. **"Azure Document Intelligence credentials not configured"**
   - Solution: Add AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and KEY to .env

2. **"401 Unauthorized"**
   - Solution: Check API key is correct and active

3. **"429 Too Many Requests"**
   - Solution: You've hit rate limit. Upgrade pricing tier or wait

4. **"Invalid content type"**
   - Solution: Ensure file is actually a PDF

### Graceful Degradation

If OCR is unavailable (not configured or API down), the system will:
1. Log a warning
2. Return PyPDF2 text extraction (may be empty for scanned PDFs)
3. Continue processing without failing

## Monitoring

### Important Metrics to Track

1. **OCR Usage Rate**: How many PDFs trigger OCR vs PyPDF2
2. **OCR Success Rate**: Percentage of successful OCR extractions
3. **Processing Time**: Average time for OCR vs PyPDF2
4. **API Costs**: Monthly Azure Document Intelligence charges

### Log Analysis

Search logs for:
- `"Attempting OCR extraction"` - OCR triggered
- `"OCR extraction successful"` - OCR completed
- `"OCR extraction failed"` - OCR errors
- `"Using PyPDF2 extraction"` - Text-based PDF (no OCR needed)

## Best Practices

1. **Choose the right region**: Deploy Azure resources close to your users
2. **Monitor costs**: Set up Azure Cost Alerts
3. **Start with Free tier**: Test with F0 before upgrading to S0
4. **Optimize PDFs**: Compress scanned PDFs to reduce pages (e.g., remove blank pages)
5. **Set alerts**: Monitor for API errors and rate limits
6. **Test thoroughly**: Upload various PDF types during testing

## Security

- **API Keys**: Never commit `.env` files to version control
- **Network**: Azure Document Intelligence uses HTTPS by default
- **Data Privacy**: PDFs sent to Azure are processed and not stored permanently
- **Compliance**: Azure Document Intelligence is compliant with GDPR, HIPAA, SOC 2, etc.

## Additional Resources

- [Azure Document Intelligence Documentation](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/)
- [Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/)
- [Language Support](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support)
- [Service Limits](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits)

## Support

For issues with:
- **LUMEN OCR integration**: Check application logs and this guide
- **Azure Document Intelligence**: Contact Azure Support
- **Billing questions**: Azure Portal → Cost Management
