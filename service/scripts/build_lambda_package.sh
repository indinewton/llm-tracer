#!/bin/bash

# Build Lambda deployment package for llm-tracer service
#
# Creates a zip file containing:
# - python dependencies (installed via pip)
# - Application source code
# - Lambda handler
#
# Prerequisites: uv (https://github.com/astral-sh/uv)
# Output: dist/lambda.zip

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$SERVICE_DIR/dist"
PACKAGE_DIR="$DIST_DIR/package"

echo "====================================="
echo "Building Lambda Package"
echo "====================================="
echo "Service directors: $SERVICE_DIR"
echo "Output: $DIST_DIR/lambda.zip"
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install uv from https://github.com/astral-sh/uv"
    exit 1
fi

# Clean previous builds (there can only be one build at any time)
echo "1. Cleaning previous build..."
rm -rf "$DIST_DIR"
mkdir -p "$PACKAGE_DIR"

cd "$SERVICE_DIR"

# Install dependencies
echo "2. Exporting dependencies from uv.lock..."
uv export --no-dev --no-hashes --no-emit-project -o "$DIST_DIR/requirements.txt"
# Echo output like: Exported 123 dependencies
echo "  Exported $(wc -l < "$DIST_DIR/requirements.txt" | tr -d ' ') dependencies"

# Install dependencies for Lambda (linux x86_64)
echo "3. Installing dependencies for Lambda (linux x86_64)..."
uv pip install \
    --target "$PACKAGE_DIR" \
    --python-platform x86_64-manylinux_2_17 \
    --python-version 3.12 \
    --no-deps \
    -r "$DIST_DIR/requirements.txt"

# Install with deps (some packages need transitive dependencies)
# Run again without --no-deps to get everything
uv pip install \
    --target "$PACKAGE_DIR" \
    --python-platform x86_64-manylinux_2_17 \
    --python-version 3.12 \
    -r "$DIST_DIR/requirements.txt"


# Remove unnecessary files to reduce package size
echo "4. Removing unnecessary files..."
find "$PACKAGE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name "*.so" -name "*test*" -delete 2>/dev/null || true

# Remove boto3/botocore (Lambda runtime provides these - albeit lagging behind python releases in months)
# Enable it only when you are working with latest LLM services in AWS bedrock models; and use S3
# echo "5. Removing boto3/botocore (provided by Lambda runtime)..."
# rm -rf "$PACKAGE_DIR/boto3" 2>/dev/null || true
# rm -rf "$PACKAGE_DIR/botocore" 2>/dev/null || true
# rm -rf "$PACKAGE_DIR/boto3-"* 2>/dev/null || true
# rm -rf "$PACKAGE_DIR/botocore-"* 2>/dev/null || true

# Copy application source code (copy entire src/ directory to preserve module structure)
echo "6. Copying application source code..."
cp -r "$SERVICE_DIR/src" "$PACKAGE_DIR/"

# Copy Lambda Handler to root of package
echo "7. Copying Lambda Handler to root of package..."
cp "$SERVICE_DIR/lambda_handler.py" "$PACKAGE_DIR/"

# Create zip file
echo "8. Creating zip file..."
cd "$PACKAGE_DIR"
zip -r -q "$DIST_DIR/lambda.zip" . -x "*.pyc" -x "__pycache__/*" -x "*.so.debug"

# Cleanup
rm -rf "$PACKAGE_DIR"
rm -f "$DIST_DIR/requirements.txt"

# Show results
echo ""
echo "=============================================="
echo "Build completed successfully!"
echo "=============================================="
PACKAGE_SIZE=$(du -h "$DIST_DIR/lambda.zip" | cut -f1)
echo "Package: $DIST_DIR/lambda.zip"
echo "Package size: $PACKAGE_SIZE"
echo ""
echo "Lambda size limits:"
echo "  - Direct upload: 50 MB (zipped)"
echo "  - With S3: 250 MB (unzipped)"
echo ""

# Verify package size
PACKAGE_BYTES=$(stat -f%z "$DIST_DIR/lambda.zip" 2>/dev/null || stat -c%s "$DIST_DIR/lambda.zip" 2>/dev/null)
MAX_BYTES=$((50 * 1024 * 1024))  # 50 MB

if [ "$PACKAGE_BYTES" -gt "$MAX_BYTES" ]; then
    echo "WARNING: Package exceeds 50 MB direct upload limit. Consider using S3 deployment."
    echo "Alternatively: you can reduce dependencies on heavy packages."
    exit 1
fi

echo "Package is within Lambda limits."
echo ""
echo "Build completed successfully! NEXT STEPS..."
echo " cd infrastructure/environments/dev && terraform apply"