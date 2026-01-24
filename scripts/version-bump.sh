#!/bin/bash

# Version Bump Script for POS Next
# Usage: ./scripts/version-bump.sh [major|minor|patch]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# File paths
INIT_FILE="$PROJECT_ROOT/pos_next/__init__.py"
PACKAGE_JSON="$PROJECT_ROOT/POS/package.json"

# Check if files exist
if [ ! -f "$INIT_FILE" ]; then
    print_error "Cannot find $INIT_FILE"
    exit 1
fi

if [ ! -f "$PACKAGE_JSON" ]; then
    print_error "Cannot find $PACKAGE_JSON"
    exit 1
fi

# Get current version from __init__.py
CURRENT_VERSION=$(grep -oP '__version__\s*=\s*"\K[^"]+' "$INIT_FILE")

if [ -z "$CURRENT_VERSION" ]; then
    print_error "Could not extract current version from $INIT_FILE"
    exit 1
fi

print_info "Current version: $CURRENT_VERSION"

# Parse version components
IFS='.' read -r -a VERSION_PARTS <<< "$CURRENT_VERSION"
MAJOR="${VERSION_PARTS[0]}"
MINOR="${VERSION_PARTS[1]}"
PATCH="${VERSION_PARTS[2]}"

# Determine version bump type
BUMP_TYPE="${1:-patch}"

case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
    *)
        print_error "Invalid bump type: $BUMP_TYPE"
        echo "Usage: $0 [major|minor|patch]"
        exit 1
        ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"

print_info "Bumping version from $CURRENT_VERSION to $NEW_VERSION ($BUMP_TYPE)"

# Confirm with user
read -p "Continue with version bump? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Version bump cancelled"
    exit 0
fi

# Update __init__.py
print_info "Updating $INIT_FILE..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS requires empty string after -i
    sed -i '' "s/__version__ = \"$CURRENT_VERSION\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"
else
    sed -i "s/__version__ = \"$CURRENT_VERSION\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"
fi
print_success "Updated __init__.py"

# Update package.json
print_info "Updating $PACKAGE_JSON..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/\"version\": \"$CURRENT_VERSION\"/\"version\": \"$NEW_VERSION\"/" "$PACKAGE_JSON"
else
    sed -i "s/\"version\": \"$CURRENT_VERSION\"/\"version\": \"$NEW_VERSION\"/" "$PACKAGE_JSON"
fi
print_success "Updated package.json"

# Display summary
echo
echo "════════════════════════════════════════"
print_success "Version bump completed!"
echo "════════════════════════════════════════"
print_info "Old version: $CURRENT_VERSION"
print_info "New version: $NEW_VERSION"
print_info "Bump type: $BUMP_TYPE"
echo
print_warning "Next steps:"
echo "  1. Review the changes"
echo "  2. Build the frontend: cd POS && yarn build"
echo "  3. Commit the changes: git add . && git commit -m \"chore: bump version to $NEW_VERSION\""
echo "  4. Tag the release: git tag v$NEW_VERSION"
echo "  5. Push changes: git push && git push --tags"
echo
