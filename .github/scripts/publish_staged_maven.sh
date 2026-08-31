#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077

internal_origin="https://kkrepo-internal.kkrepo.svc.cluster.local"
hosted_repository="suvio-public-releases"
group_repository="suvio-maven-public"
credential_directory="/run/secrets/kkrepo-publisher"
ca_file="/run/trust/kkrepo/ca.crt"

if [[ "$#" -ne 2 ]]; then
  echo "Usage: $0 <verified-stage-directory> <immutable-version>" >&2
  exit 2
fi

stage_directory="$1"
release_version="$2"

if [[ ! "${release_version}" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+([.][0-9A-Za-z-]+)*)?$ ]] ||
  [[ "${release_version}" == *SNAPSHOT* ]]; then
  echo "Refusing a mutable or malformed runtime version." >&2
  exit 1
fi

for required_command in chmod cmp curl find grep mktemp rm sed sha256sum sort tr uniq wc; do
  if ! command -v "${required_command}" >/dev/null 2>&1; then
    echo "Required publication command is missing: ${required_command}" >&2
    exit 1
  fi
done

username_file="${credential_directory}/username"
password_file="${credential_directory}/password"
manifest_file="${stage_directory}/SHA256SUMS"

if [[ ! -d "${stage_directory}" || -L "${stage_directory}" || ! -f "${manifest_file}" || -L "${manifest_file}" ]]; then
  echo "The verified runtime staging directory or checksum inventory is missing." >&2
  exit 1
fi
if [[ ! -s "${username_file}" || ! -s "${password_file}" || ! -r "${ca_file}" ]]; then
  echo "A required publisher credential or CA file is unavailable." >&2
  exit 1
fi

temporary_directory="$(mktemp -d /dev/shm/suvio-runtime-maven-publish.XXXXXX)"
cleanup() {
  set +e
  case "${temporary_directory}" in
    /dev/shm/suvio-runtime-maven-publish.*)
      rm -rf -- "${temporary_directory}"
      ;;
  esac
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

netrc_file="${temporary_directory}/credentials.netrc"
{
  printf 'machine kkrepo-internal.kkrepo.svc.cluster.local login '
  tr -d '\r\n' <"${username_file}"
  printf ' password '
  tr -d '\r\n' <"${password_file}"
  printf '\n'
} >"${netrc_file}"
chmod 0600 "${netrc_file}"

listed_paths="${temporary_directory}/listed-paths"
actual_paths="${temporary_directory}/actual-paths"
upload_payloads="${temporary_directory}/upload-payloads"
upload_poms="${temporary_directory}/upload-poms"
: >"${listed_paths}"
: >"${upload_payloads}"
: >"${upload_poms}"

while IFS= read -r inventory_line || [[ -n "${inventory_line}" ]]; do
  inventory_hash="${inventory_line%%  *}"
  inventory_path="${inventory_line#*  }"
  if [[ "${inventory_hash}" == "${inventory_line}" ]] ||
    [[ ! "${inventory_hash}" =~ ^[0-9a-f]{64}$ ]] ||
    [[ ! "${inventory_path}" =~ ^[A-Za-z0-9._/-]+$ ]] ||
    [[ "${inventory_path}" == /* || "${inventory_path}" == *".."* ]]; then
    echo "The runtime checksum inventory contains an unsafe entry." >&2
    exit 1
  fi
  printf '%s\n' "${inventory_path}" >>"${listed_paths}"
done <"${manifest_file}"

if [[ ! -s "${listed_paths}" ]]; then
  echo "The runtime checksum inventory is empty." >&2
  exit 1
fi
if [[ -n "$(LC_ALL=C sort "${listed_paths}" | uniq -d)" ]]; then
  echo "The runtime checksum inventory contains duplicate paths." >&2
  exit 1
fi
if [[ -n "$(find "${stage_directory}" -type l -print -quit)" ]]; then
  echo "The runtime staging tree contains a symbolic link." >&2
  exit 1
fi
(
  cd "${stage_directory}"
  find . -type f ! -path './SHA256SUMS' -print |
    sed 's#^\./##' |
    LC_ALL=C sort
) >"${actual_paths}"
LC_ALL=C sort "${listed_paths}" -o "${listed_paths}"
if ! cmp -s "${listed_paths}" "${actual_paths}"; then
  echo "The runtime checksum inventory does not exactly cover the staging tree." >&2
  exit 1
fi
if ! (cd "${stage_directory}" && sha256sum --check --strict --quiet SHA256SUMS); then
  echo "The runtime staging checksum verification failed." >&2
  exit 1
fi

while IFS= read -r relative_path; do
  case "${relative_path}" in
    .nojekyll | */maven-metadata.xml | */maven-metadata.xml.*)
      continue
      ;;
  esac
  case "${relative_path}" in
    cc/suviomedia/kmedia-ass-runtime-android/"${release_version}"/* | \
      cc/suviomedia/kmedia-ass-runtime-desktop/"${release_version}"/* | \
      cc/suviomedia/kmedia-ffmpeg-runtime-android/"${release_version}"/* | \
      cc/suviomedia/kmedia-ffmpeg-runtime-desktop/"${release_version}"/*)
      ;;
    *)
      echo "The runtime staging tree escaped the four reviewed Maven coordinates." >&2
      exit 1
      ;;
  esac
  if [[ "${relative_path}" == *.pom ]]; then
    printf '%s\n' "${relative_path}" >>"${upload_poms}"
  else
    printf '%s\n' "${relative_path}" >>"${upload_payloads}"
  fi
done <"${listed_paths}"

if [[ ! -s "${upload_payloads}" || "$(wc -l <"${upload_poms}" | tr -d ' ')" -ne 4 ]]; then
  echo "The runtime staging tree does not contain four complete Maven releases." >&2
  exit 1
fi

internal_status() {
  local request_method="$1"
  local request_url="$2"
  if [[ "${request_method}" != HEAD || "${request_url}" != "${internal_origin}"/* ]]; then
    echo "Refusing an unsupported runtime Maven preflight request." >&2
    return 1
  fi
  curl \
    --disable \
    --silent \
    --show-error \
    --noproxy '*' \
    --connect-timeout 10 \
    --max-time 120 \
    --head \
    --netrc-file "${netrc_file}" \
    --cacert "${ca_file}" \
    --proto '=https' \
    --tlsv1.2 \
    --output /dev/null \
    --write-out '%{http_code}' \
    --url "${request_url}"
}

publish_one() {
  local relative_path="$1"
  local local_file="${stage_directory}/${relative_path}"
  local target_url="${internal_origin}/repository/${hosted_repository}/${relative_path}"
  local status=""
  local local_digest=""
  local remote_digest=""

  status="$(internal_status HEAD "${target_url}")"
  case "${status}" in
    200)
      local_digest="$(sha256sum "${local_file}" | sed 's/[[:space:]].*$//')"
      remote_digest="$(
        curl \
          --disable \
          --fail \
          --silent \
          --show-error \
          --noproxy '*' \
          --connect-timeout 10 \
          --max-time 300 \
          --netrc-file "${netrc_file}" \
          --cacert "${ca_file}" \
          --proto '=https' \
          --tlsv1.2 \
          --url "${target_url}" |
          sha256sum |
          sed 's/[[:space:]].*$//'
      )"
      if [[ "${remote_digest}" != "${local_digest}" ]]; then
        echo "Refusing to replace an existing public runtime path with different bytes." >&2
        exit 1
      fi
      reused_count=$((reused_count + 1))
      return
      ;;
    404)
      ;;
    *)
      echo "Runtime Maven preflight returned HTTP ${status}; expected 200 or 404." >&2
      exit 1
      ;;
  esac

  status="$(
    curl \
      --disable \
      --silent \
      --show-error \
      --noproxy '*' \
      --connect-timeout 10 \
      --max-time 600 \
      --request PUT \
      --upload-file "${local_file}" \
      --netrc-file "${netrc_file}" \
      --cacert "${ca_file}" \
      --proto '=https' \
      --tlsv1.2 \
      --output /dev/null \
      --write-out '%{http_code}' \
      --url "${target_url}"
  )"
  if [[ "${status}" != 201 ]]; then
    echo "Runtime Maven upload returned HTTP ${status}; expected 201. No automatic PUT retry was attempted." >&2
    exit 1
  fi
  published_count=$((published_count + 1))
}

published_count=0
reused_count=0
while IFS= read -r relative_path; do
  publish_one "${relative_path}"
done <"${upload_payloads}"
while IFS= read -r relative_path; do
  publish_one "${relative_path}"
done <"${upload_poms}"

for verification_artifact in \
  kmedia-ass-runtime-android \
  kmedia-ass-runtime-desktop \
  kmedia-ffmpeg-runtime-android \
  kmedia-ffmpeg-runtime-desktop; do
  verification_path="cc/suviomedia/${verification_artifact}/${release_version}/${verification_artifact}-${release_version}.pom"
  verification_status="$(internal_status HEAD "${internal_origin}/repository/${group_repository}/${verification_path}")"
  if [[ "${verification_status}" != 200 ]]; then
    echo "A published runtime POM is not resolvable through the public Maven group." >&2
    exit 1
  fi
done

echo "PASS: immutable runtime Maven release published through the dedicated public-release-only identity."
echo "Uploaded files: ${published_count}; already-identical files: ${reused_count}; repository metadata was intentionally not replaced."
