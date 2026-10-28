set -e
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1 && echo ALIAS_OK
mc ls local
echo "-- quarantine objects:"
mc ls --recursive local/pofa-quarantine | wc -l
echo "-- evidence objects:"
mc ls --recursive local/pofa-evidence | wc -l
