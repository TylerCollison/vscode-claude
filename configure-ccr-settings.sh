#!/usr/bin/with-contenv bash

ccr restart
mkdir -p /config/.claude-code-router/presets
cp -r /ccr-presets/* /config/.claude-code-router/presets/

echo "Starting environment variable substitution for CCR presets..."

# Use temporary files to track counts
processed_file="/tmp/processed_count.$$"
failed_file="/tmp/failed_count.$$"
echo "0" > "$processed_file"
echo "0" > "$failed_file"

# Recursively process all JSON files using envsubst
find /config/.claude-code-router/presets -name "*.json" -type f | while read -r file; do
    # Create temporary file for processing
    temp_file="$(mktemp)"

    # Use envsubst for environment variable substitution
    if envsubst < "$file" > "$temp_file" 2>/dev/null; then
        # Basic validation: check if the file contains text (not empty)
        if [ -s "$temp_file" ] && grep -q '[^[:space:]]' "$temp_file"; then
            mv "$temp_file" "$file"
            echo "✓ Processed: $(basename "$file")"
            # Increment processed count
            count=$(cat "$processed_file")
            echo "$((count + 1))" > "$processed_file"
        else
            rm -f "$temp_file"
            echo "✗ Empty output: $(basename "$file")"
            # Increment failed count
            count=$(cat "$failed_file")
            echo "$((count + 1))" > "$failed_file"
        fi
    else
        rm -f "$temp_file"
        echo "✗ Processing failed: $(basename "$file")"
        # Increment failed count
        count=$(cat "$failed_file")
        echo "$((count + 1))" > "$failed_file"
    fi
done

# Read final counts
processed_count=$(cat "$processed_file")
failed_count=$(cat "$failed_file")

# Clean up temporary files
rm -f "$processed_file" "$failed_file"

echo "Environment variable substitution completed:"
echo "- Successfully processed: $processed_count files"
echo "- Failed: $failed_count files"

# Verify at least one file was processed successfully
if [ $processed_count -eq 0 ]; then
    echo "Warning: No files were successfully processed"
fi

# Grant open permissions for the config folder
chmod -R 777 /config

# This script runs as a pre-start hook, no need to exec commands