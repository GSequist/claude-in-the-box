#!/bin/bash
set -e

if [ $# -lt 3 ]; then
    echo "Usage: $0 <docker-image> <output-file> <size-mb>"
    exit 1
fi

DOCKER_IMAGE=$1
OUTPUT_FILE=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
SIZE_MB=$3

echo "Converting $DOCKER_IMAGE to ext4 filesystem..."

WORK_DIR=$(mktemp -d)
cd "$WORK_DIR"

echo "Exporting Docker image..."
docker save "$DOCKER_IMAGE" -o image.tar

cat > convert.sh <<'INNEREOF'
#!/bin/bash
set -e

SIZE_MB=$1
OUTPUT=/output/rootfs.ext4

echo "=== Phase 1: Creating ext4 filesystem ==="
dd if=/dev/zero of="$OUTPUT" bs=1M count="$SIZE_MB"

# -i 8192: Creates one inode per 8KB (more inodes for Python packages with many small files)
mkfs.ext4 -F -O "^dir_index,^64bit,^dir_nlink,^metadata_csum,ext_attr,sparse_super2,filetype,extent,flex_bg,large_file,huge_file,extra_isize" -b 4096 -m 0 -i 8192 "$OUTPUT"

echo "=== Phase 2: Mounting ext4 ==="
mkdir -p /mnt/rootfs
mount -o loop "$OUTPUT" /mnt/rootfs

echo "=== Phase 3: Extracting Docker layers with whiteout handling ==="
cd /mnt/rootfs
tar -xf /input/image.tar

# Extract each layer and process whiteouts
for layer in $(cat manifest.json | jq -r '.[0].Layers[]'); do
    echo "Extracting layer: $layer"
    tar -xf "$layer"

    # Handle whiteout files (.wh.filename removes the actual file)
    find . -name '.wh.*' ! -name '.wh..wh..opq' -type f 2>/dev/null | while read whfile; do
        target=$(dirname "$whfile")/$(basename "$whfile" | sed 's/^\.wh\.//')
        echo "  Removing whited-out file: $target"
        rm -rf "$target" 2>/dev/null || true
        rm -f "$whfile"
    done

    # Handle opaque directories (.wh..wh..opq makes directory opaque)
    find . -name '.wh..wh..opq' -type f 2>/dev/null | while read opqfile; do
        dir=$(dirname "$opqfile")
        echo "  Processing opaque directory: $dir"
        rm -f "$opqfile"
    done
done

# Clean up Docker tar metadata
rm -rf manifest.json repositories blobs oci-layout 2>/dev/null || true

cd /

echo "=== Phase 4: Syncing and unmounting ==="
sync
sleep 1
umount /mnt/rootfs
sync

echo "=== Phase 5: Filesystem integrity check ==="
e2fsck -f -y "$OUTPUT" || echo "Note: Minor errors fixed"

echo "=== Phase 6: Optimizing filesystem size ==="
echo "Shrinking to minimum size..."
resize2fs -M "$OUTPUT"

CURRENT_SIZE=$(dumpe2fs -h "$OUTPUT" 2>/dev/null | grep "Block count:" | awk '{print $3}')
BLOCK_SIZE=$(dumpe2fs -h "$OUTPUT" 2>/dev/null | grep "Block size:" | awk '{print $3}')
CURRENT_MB=$((CURRENT_SIZE * BLOCK_SIZE / 1024 / 1024))

echo "Current size: ${CURRENT_MB}MB, Target: ${SIZE_MB}MB"

if [ "$CURRENT_MB" -lt "$SIZE_MB" ]; then
    echo "Enlarging to target size..."
    resize2fs "$OUTPUT" "${SIZE_MB}M"
    e2fsck -f -y "$OUTPUT" || true
fi

FREE_BLOCKS=$(dumpe2fs -h "$OUTPUT" 2>/dev/null | grep "Free blocks:" | awk '{print $3}')
FREE_MB=$((FREE_BLOCKS * BLOCK_SIZE / 1024 / 1024))
echo "Free space: ${FREE_MB}MB"

sync

echo "✅ Conversion complete!"
INNEREOF

chmod +x convert.sh

echo "Running conversion in privileged container..."
docker run --rm --privileged \
    -v "$WORK_DIR:/input" \
    -v "$(dirname "$OUTPUT_FILE"):/output" \
    ubuntu:22.04 \
    bash -c "
        apt-get update -qq &&
        apt-get install -y -qq e2fsprogs jq > /dev/null &&
        /input/convert.sh $SIZE_MB
    "

mv "$(dirname "$OUTPUT_FILE")/rootfs.ext4" "$OUTPUT_FILE"

cd /
rm -rf "$WORK_DIR"

echo ""
echo "✅ Created $OUTPUT_FILE"
ls -lh "$OUTPUT_FILE"
echo ""

