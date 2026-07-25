#!/usr/bin/env bash
# Run GraphRAG API and worker natively in WSL so they can use the Windows
# loopback-forwarded LM Studio endpoint. Persistent stores remain in Compose.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
runtime_dir="${project_root}/.runtime"
mode="${1:-}"

usage() {
    echo "usage: $0 {start|stop|status}" >&2
    exit 2
}

read_env_value() {
    local key="$1"
    local value
    value="$(sed -n "s/^${key}=//p" "${project_root}/.env" | head -n 1)"
    if [[ -z "${value}" ]]; then
        echo "Missing ${key} in ${project_root}/.env" >&2
        exit 1
    fi
    printf '%s' "${value}"
}

pid_is_ours() {
    local pid="$1"
    [[ -d "/proc/${pid}" ]] || return 1
    [[ "$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)" == "${project_root}" ]]
}

stop_component() {
    local name="$1"
    local pid_file="${runtime_dir}/${name}.pid"
    [[ -f "${pid_file}" ]] || return 0

    local pid
    pid="$(<"${pid_file}")"
    if ! pid_is_ours "${pid}"; then
        rm -f -- "${pid_file}"
        return 0
    fi

    kill -TERM "${pid}"
    for _ in {1..30}; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            rm -f -- "${pid_file}"
            return 0
        fi
        sleep 1
    done
    echo "${name} (PID ${pid}) did not stop within 30 seconds." >&2
    return 1
}

start_component() {
    local name="$1"
    shift
    local pid_file="${runtime_dir}/${name}.pid"
    local log_file="${runtime_dir}/${name}.log"

    if [[ -f "${pid_file}" ]] && pid_is_ours "$(<"${pid_file}")"; then
        echo "${name} is already running (PID $(<"${pid_file}"))." >&2
        return 0
    fi
    rm -f -- "${pid_file}"
    # `setsid -f` detaches from the WSL command session. A plain background
    # process is otherwise terminated when the Windows launcher exits.
    setsid -f bash -c '
        project_root="$1"
        pid_file="$2"
        shift 2
        cd -- "${project_root}"
        printf "%s\n" "$$" > "${pid_file}"
        exec "$@"
    ' bash "${project_root}" "${pid_file}" "$@" >>"${log_file}" 2>&1 < /dev/null

    local pid=""
    for _ in {1..10}; do
        if [[ -f "${pid_file}" ]]; then
            pid="$(<"${pid_file}")"
            if pid_is_ours "${pid}"; then
                echo "${name} started (PID ${pid})."
                return 0
            fi
        fi
        sleep 1
    done
    rm -f -- "${pid_file}"
    echo "${name} failed to start; see ${log_file}." >&2
    return 1
}

case "${mode}" in
    start)
        [[ -f "${project_root}/.env" ]] || {
            echo "Missing ${project_root}/.env" >&2
            exit 1
        }
        [[ -x "${project_root}/.venv/bin/python" ]] || {
            echo "Missing ${project_root}/.venv/bin/python" >&2
            exit 1
        }
        mkdir -p -- "${runtime_dir}"

        pg_user="$(read_env_value GKS_POSTGRES_USER)"
        pg_password="$(read_env_value GKS_POSTGRES_PASSWORD)"
        pg_database="$(read_env_value GKS_POSTGRES_DB)"
        pg_port="$(read_env_value GKS_POSTGRES_PORT)"
        neo4j_password="$(read_env_value GKS_NEO4J_PASSWORD)"

        export GKS_POSTGRES_DSN="postgresql+psycopg://${pg_user}:${pg_password}@127.0.0.1:${pg_port}/${pg_database}"
        export GKS_NEO4J_PASSWORD="${neo4j_password}"
        export GKS_API_HOST="127.0.0.1"
        export GKS_GENERATION_PROVIDER_URL="http://127.0.0.1:1234/v1"
        export GKS_EMBEDDING_PROVIDER_URL="http://127.0.0.1:1234/v1"
        export GKS_WORKER_ID="graphrag-native-worker"

        start_component api "${project_root}/.venv/bin/python" -m graphrag_service.api.cli
        start_component worker "${project_root}/.venv/bin/python" -m graphrag_service.workers.cli
        ;;
    stop)
        [[ -d "${runtime_dir}" ]] || exit 0
        stop_component worker
        stop_component api
        ;;
    status)
        for name in api worker; do
            pid_file="${runtime_dir}/${name}.pid"
            if [[ -f "${pid_file}" ]] && pid_is_ours "$(<"${pid_file}")"; then
                echo "${name}: running (PID $(<"${pid_file}"))"
            else
                echo "${name}: stopped"
            fi
        done
        ;;
    *) usage ;;
esac
