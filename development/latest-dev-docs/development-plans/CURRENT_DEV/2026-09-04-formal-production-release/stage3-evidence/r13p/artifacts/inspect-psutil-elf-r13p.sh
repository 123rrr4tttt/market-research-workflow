#!/usr/bin/env bash
set -u

SOURCE=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/artifacts
OUT=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13p/artifacts
declare -a TAGS=()

cleanup() {
  for tag in "${TAGS[@]}"; do
    docker image rm "$tag" >> "$OUT/psutil-elf-image-cleanup.log" 2>&1 || true
  done
}
trap cleanup EXIT

for role in backend migration-runner; do
  for phase in canonical rebuild; do
    archive="$SOURCE/$phase/${role}.oci.tar"
    prefix="psutil-elf-${role}-${phase}"
    printf 'docker load -i %q\n' "$archive" > "$OUT/${prefix}-load.command.txt"
    docker load -i "$archive" > "$OUT/${prefix}-load.log" 2>&1
    code=$?
    printf '%s\n' "$code" > "$OUT/${prefix}-load.exit.txt"
    [[ "$code" == 0 ]] || continue

    image_id=$(sed -n 's/^Loaded image ID: //p' "$OUT/${prefix}-load.log" | tail -n 1)
    tag="mrw-r13p-psutil-elf-${role}-${phase}:local"
    docker tag "$image_id" "$tag" >> "$OUT/${prefix}-load.log" 2>&1
    code=$?
    [[ "$code" == 0 ]] || continue
    TAGS+=("$tag")

    printf '%s\n' "docker run --rm --entrypoint /bin/sh $tag -ec <bounded ELF inspection>" > "$OUT/${prefix}.command.txt"
    docker run --rm --entrypoint /bin/sh "$tag" -ec '
      for file in \
        /usr/local/lib/python3.11/site-packages/psutil/_psutil_linux.abi3.so \
        /usr/local/lib/python3.11/site-packages/psutil/_psutil_posix.abi3.so
      do
        echo "FILE=$file"
        sha256sum "$file"
        echo "NOTES"
        readelf -n "$file"
        echo "COMMENT"
        readelf -p .comment "$file" || true
        for section in \
          .text .rodata .data .eh_frame .eh_frame_hdr \
          .dynsym .dynstr .symtab .strtab \
          .debug_info .debug_abbrev .debug_line .debug_str .debug_line_str \
          .note.gnu.build-id
        do
          target="/tmp/$(basename "$file").${section#.}.bin"
          if objcopy --dump-section "$section=$target" "$file" 2>/dev/null && test -f "$target"; then
            printf "SECTION=%s " "$section"
            sha256sum "$target"
          else
            printf "SECTION=%s ABSENT\n" "$section"
          fi
        done
        echo "BUILD_PATH_STRINGS"
        strings "$file" | grep -E "/tmp/|pip-|psutil-5\\.9\\.8" | head -n 40 || true
      done
    ' > "$OUT/${prefix}.log" 2>&1
    code=$?
    printf '%s\n' "$code" > "$OUT/${prefix}.exit.txt"
  done
done
